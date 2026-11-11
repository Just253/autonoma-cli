from __future__ import annotations

import json
import ssl
import time
import unittest
from unittest import mock
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request

from autonoma_cli import config
from autonoma_cli import net as net_module
from autonoma_cli.client import CampusClient
from autonoma_cli.errors import CampusError
from autonoma_cli.net import cert_mismatch
from support.home import IsolatedHomeMixin


class CertificateMismatchTests(unittest.TestCase):
    """El ALB del campus rota IPs: una IP vieja responde con otro certificado."""

    def test_hostname_mismatch_is_detected(self) -> None:
        error = ssl.SSLCertVerificationError(
            1,
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
            "Hostname mismatch, certificate is not valid for "
            "'virtual.autonoma.edu.pe'. (_ssl.c:1006)",
        )
        self.assertTrue(cert_mismatch(URLError(error)))

    def test_connection_refused_is_not_a_mismatch(self) -> None:
        self.assertFalse(cert_mismatch(URLError(ConnectionRefusedError(10061, "refused"))))


class RouteAroundTests(IsolatedHomeMixin, unittest.TestCase):
    """Ante un certificado ajeno, el cliente salta a otra IP y reintenta."""

    def setUp(self) -> None:
        self.make_home()

    def _client(self) -> CampusClient:
        return CampusClient(delay=0, retries=2)

    def _mismatch(self) -> URLError:
        return URLError(ssl.SSLCertVerificationError(1, "Hostname mismatch"))

    def test_reintenta_por_otra_ip(self) -> None:
        client = self._client()
        calls: list[str] = []
        routed: list[bool] = []

        def fake_open(request, timeout=None):  # noqa: ANN001, ANN202
            calls.append(request.full_url)
            if len(calls) == 1:
                raise self._mismatch()
            return "respuesta"

        def fake_route() -> bool:
            routed.append(True)
            client._pin_handler.pin_ip = "192.0.2.10"
            return True

        client._opener.open = fake_open  # type: ignore[method-assign]
        client._route_around = fake_route  # type: ignore[method-assign]

        self.assertEqual(client._open(Request("https://campus.invalid/Campus/Login.aspx")), "respuesta")
        self.assertEqual(len(routed), 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(client._pin_handler.pin_ip, "192.0.2.10")

    def test_sin_ip_valida_avisa_del_certificado(self) -> None:
        client = self._client()
        client._opener.open = lambda *a, **k: (_ for _ in ()).throw(self._mismatch())
        client._route_around = lambda: False  # type: ignore[method-assign]

        with self.assertRaises(CampusError) as raised:
            client._open(Request("https://campus.invalid/Campus/Login.aspx"))
        self.assertIn("certificado de otro sitio", str(raised.exception))


class PinnedIpTests(IsolatedHomeMixin, unittest.TestCase):
    """La IP que valido certificado se recuerda entre corridas (cache corta)."""

    def setUp(self) -> None:
        self.make_home()

    def test_la_ip_buena_se_reusa_en_la_corrida_siguiente(self) -> None:
        with mock.patch.object(net_module, "flush_dns"), mock.patch.object(
            net_module, "valid_ip", return_value="192.0.2.10"
        ):
            first = CampusClient(delay=0)
            self.assertEqual(first._pin_handler.pin_ip, "")
            self.assertTrue(first._route_around())

        second = CampusClient(delay=0)
        self.assertEqual(second._pin_handler.pin_ip, "192.0.2.10")

    def test_la_ip_vencida_se_ignora(self) -> None:
        config.pinned_path().write_text(
            json.dumps(
                {
                    "host": urlsplit(config.DEFAULT_BASE_URL).hostname,
                    "ip": "192.0.2.10",
                    "checked_at": time.time() - net_module.PINNED_TTL - 1,
                }
            ),
            encoding="utf-8",
        )
        self.assertEqual(CampusClient(delay=0)._pin_handler.pin_ip, "")

    def test_la_ip_de_otro_host_se_ignora(self) -> None:
        net_module.save_pin(config.pinned_path(), "otro.example", "192.0.2.10")
        self.assertEqual(CampusClient(delay=0)._pin_handler.pin_ip, "")

    def test_una_ip_muerta_se_descarta_y_se_reintenta(self) -> None:
        client = CampusClient(delay=0)
        client._pin_handler.pin_ip = "192.0.2.10"
        net_module.save_pin(config.pinned_path(), client._host, "192.0.2.10")
        calls: list[str] = []

        def fake_open(request, timeout=None):  # noqa: ANN001, ANN202
            calls.append(request.full_url)
            if len(calls) == 1:
                raise URLError(ConnectionRefusedError(10061, "refused"))
            return "respuesta"

        client._opener.open = fake_open  # type: ignore[method-assign]
        self.assertEqual(
            client._open(Request("https://campus.invalid/Campus/Login.aspx")), "respuesta"
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(client._pin_handler.pin_ip, "")
        self.assertFalse(config.pinned_path().exists())


if __name__ == "__main__":
    unittest.main()
