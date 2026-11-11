"""Transporte de la sesion: salto por certificado ajeno y pin de IP."""

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
from autonoma_cli.errors import CampusError
from autonoma_cli.session import CampusSession
from support.home import IsolatedHomeMixin

LOGIN_URL = "https://campus.invalid/Campus/Login.aspx"


class RouteAroundTests(IsolatedHomeMixin, unittest.TestCase):
    """Ante un certificado ajeno, la sesion salta a otra IP y reintenta."""

    def setUp(self) -> None:
        self.make_home()

    def _session(self) -> CampusSession:
        return CampusSession(
            config.DEFAULT_BASE_URL,
            delay=0,
            cookies_path=str(config.cookies_path()),
            pinned_path=config.pinned_path(),
        )

    def _mismatch(self) -> URLError:
        return URLError(ssl.SSLCertVerificationError(1, "Hostname mismatch"))

    def test_reintenta_por_otra_ip(self) -> None:
        session = self._session()
        calls: list[str] = []
        routed: list[bool] = []

        def fake_open(request, timeout=None):  # noqa: ANN001, ANN202
            calls.append(request.full_url)
            if len(calls) == 1:
                raise self._mismatch()
            return "respuesta"

        def fake_route() -> bool:
            routed.append(True)
            session.pin_ip = "192.0.2.10"
            return True

        session._opener.open = fake_open  # type: ignore[method-assign]
        session._route_around = fake_route  # type: ignore[method-assign]

        self.assertEqual(session.send(Request(LOGIN_URL)), "respuesta")
        self.assertEqual(len(routed), 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(session.pin_ip, "192.0.2.10")

    def test_sin_ip_valida_avisa_del_certificado(self) -> None:
        session = self._session()
        session._opener.open = lambda *a, **k: (_ for _ in ()).throw(self._mismatch())
        session._route_around = lambda: False  # type: ignore[method-assign]

        with self.assertRaises(CampusError) as raised:
            session.send(Request(LOGIN_URL))
        self.assertIn("certificado de otro sitio", str(raised.exception))


class PinnedIpTests(IsolatedHomeMixin, unittest.TestCase):
    """La IP que valido certificado se recuerda entre corridas (cache corta)."""

    def setUp(self) -> None:
        self.make_home()

    def _session(self) -> CampusSession:
        return CampusSession(
            config.DEFAULT_BASE_URL,
            delay=0,
            cookies_path=str(config.cookies_path()),
            pinned_path=config.pinned_path(),
        )

    def test_la_ip_buena_se_reusa_en_la_corrida_siguiente(self) -> None:
        with mock.patch.object(net_module, "flush_dns"), mock.patch.object(
            net_module, "valid_ip", return_value="192.0.2.10"
        ):
            first = self._session()
            self.assertEqual(first.pin_ip, "")
            self.assertTrue(first._route_around())

        second = self._session()
        self.assertEqual(second.pin_ip, "192.0.2.10")

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
        self.assertEqual(self._session().pin_ip, "")

    def test_la_ip_de_otro_host_se_ignora(self) -> None:
        net_module.save_pin(config.pinned_path(), "otro.example", "192.0.2.10")
        self.assertEqual(self._session().pin_ip, "")

    def test_una_ip_muerta_se_descarta_y_se_reintenta(self) -> None:
        session = self._session()
        session.pin_ip = "192.0.2.10"
        net_module.save_pin(config.pinned_path(), session.host, "192.0.2.10")
        calls: list[str] = []

        def fake_open(request, timeout=None):  # noqa: ANN001, ANN202
            calls.append(request.full_url)
            if len(calls) == 1:
                raise URLError(ConnectionRefusedError(10061, "refused"))
            return "respuesta"

        session._opener.open = fake_open  # type: ignore[method-assign]
        self.assertEqual(session.send(Request(LOGIN_URL)), "respuesta")
        self.assertEqual(len(calls), 2)
        self.assertEqual(session.pin_ip, "")
        self.assertFalse(config.pinned_path().exists())


if __name__ == "__main__":
    unittest.main()
