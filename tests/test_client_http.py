from __future__ import annotations

import ssl
import unittest
from urllib.error import URLError
from urllib.request import Request

from autonoma_cli.client import CampusClient, _cert_mismatch
from autonoma_cli.errors import CampusError


class CertificateMismatchTests(unittest.TestCase):
    """El ALB del campus rota IPs: una IP vieja responde con otro certificado."""

    def test_hostname_mismatch_is_detected(self) -> None:
        error = ssl.SSLCertVerificationError(
            1,
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
            "Hostname mismatch, certificate is not valid for "
            "'virtual.autonoma.edu.pe'. (_ssl.c:1006)",
        )
        self.assertTrue(_cert_mismatch(URLError(error)))

    def test_connection_refused_is_not_a_mismatch(self) -> None:
        self.assertFalse(_cert_mismatch(URLError(ConnectionRefusedError(10061, "refused"))))


class RouteAroundTests(unittest.TestCase):
    """Ante un certificado ajeno, el cliente salta a otra IP y reintenta."""

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


if __name__ == "__main__":
    unittest.main()
