"""Politica de llamadas: un pedido, reintentos, relogin y subida unica."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest import mock

from autonoma_cli.api import ApiContext, call, call_once, post_raw
from autonoma_cli.errors import (
    AuthenticationError,
    CampusError,
    CampusHTTPError,
    ProtocolError,
    SessionExpiredError,
)
from support.session import FakeSession

BASE = "https://campus-de-ejemplo.edu"
HOME_URL = f"{BASE}/Campus/Default.aspx"
LOGIN_URL = f"{BASE}/Campus/Login.aspx?ReturnUrl=%2fCampus%2fDefault.aspx"


class FakeResponse:
    def __init__(self, body: bytes, url: str = HOME_URL) -> None:
        self.body = body
        self.url = url

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def geturl(self) -> str:
        return self.url

    def read(self) -> bytes:
        return self.body


class FakeAuth:
    """Auth de mentira: cuenta relogins y expiraciones sin tocar la red."""

    def __init__(self, *, authenticated: bool = True, credentials: bool = True) -> None:
        self.authenticated = authenticated
        self.credentials = credentials
        self.expired = 0
        self.relogins = 0

    def relogin(self) -> None:
        if not self.credentials:
            raise SessionExpiredError(
                "La sesion del campus expiro y no hay credenciales para renovarla. "
                "Ejecuta: autonoma login"
            )
        self.relogins += 1
        self.authenticated = True

    def expire(self) -> None:
        self.expired += 1
        self.authenticated = False


def _ctx(*responses: object, retries: int = 3, authenticated: bool = True):
    session = FakeSession(*responses)
    session.home_url = HOME_URL
    auth = FakeAuth(authenticated=authenticated)
    return ApiContext(BASE, {"User-Agent": "prueba"}, session, auth, retries), session, auth


class CallOnceTests(unittest.TestCase):
    def test_arma_el_pedido_y_desenvuelve(self) -> None:
        ctx, session, _ = _ctx(FakeResponse(b'{"d": {"ok": true}}'))

        result = call_once(ctx, "Metodo", {"a": 1}, "/Campus/Default.aspx")

        self.assertEqual(result, {"ok": True})
        request = session.requests[-1]
        self.assertEqual(request.full_url, f"{HOME_URL}/Metodo")
        self.assertEqual(request.get_header("Referer"), HOME_URL)
        self.assertEqual(request.get_header("Content-type"), "application/json; charset=utf-8")
        self.assertEqual(json.loads(request.data), {"a": 1})

    def test_respuesta_vacia_no_es_error(self) -> None:
        ctx, _, _ = _ctx(FakeResponse(b"   "))
        self.assertIsNone(call_once(ctx, "Metodo", {}, "/Campus/Default.aspx"))

    def test_sin_json_es_error_de_protocolo(self) -> None:
        ctx, _, _ = _ctx(FakeResponse(b"<html>error</html>"))
        with self.assertRaises(ProtocolError) as raised:
            call_once(ctx, "Metodo", {}, "/Campus/Default.aspx")
        self.assertIn("Metodo no devolvio JSON", str(raised.exception))

    def test_redirigido_al_login_es_sesion_vencida(self) -> None:
        ctx, _, _ = _ctx(FakeResponse(b"", LOGIN_URL))
        with self.assertRaises(SessionExpiredError) as raised:
            call_once(ctx, "Metodo", {}, "/Campus/Default.aspx")
        self.assertEqual(str(raised.exception), "La sesion del campus expiro.")


class CallTests(unittest.TestCase):
    def test_reintenta_los_5xx_hasta_el_tope(self) -> None:
        ctx, session, _ = _ctx(CampusHTTPError("500", 500), retries=2)
        with mock.patch("autonoma_cli.api.call.time.sleep"):
            with self.assertRaises(CampusHTTPError):
                call(ctx, "Metodo")
        self.assertEqual(session.attempts, 2)

    def test_sin_reintento_transitorio_hace_un_solo_intento(self) -> None:
        ctx, session, _ = _ctx(CampusHTTPError("500", 500))
        with self.assertRaises(CampusHTTPError):
            call(ctx, "Metodo", retry_transient=False)
        self.assertEqual(session.attempts, 1)

    def test_un_401_renueva_la_cookie_y_repite(self) -> None:
        ctx, session, auth = _ctx(
            CampusHTTPError("401", 401), FakeResponse(b'{"d": 1}')
        )

        self.assertEqual(call(ctx, "Metodo"), 1)
        self.assertEqual((auth.expired, auth.relogins), (1, 1))
        self.assertEqual(session.attempts, 2)

    def test_un_401_sin_relogin_es_sesion_vencida(self) -> None:
        ctx, session, auth = _ctx(CampusHTTPError("401", 401))
        with self.assertRaises(SessionExpiredError):
            call(ctx, "Metodo", allow_relogin=False)
        self.assertEqual((auth.expired, auth.relogins, session.attempts), (1, 0, 1))

    def test_si_la_sesion_no_esta_autenticada_reloguea_primero(self) -> None:
        ctx, session, auth = _ctx(FakeResponse(b'{"d": 1}'), authenticated=False)

        self.assertEqual(call(ctx, "Metodo"), 1)
        self.assertEqual((auth.relogins, session.attempts), (1, 1))

    def test_un_error_de_autenticacion_no_se_reintenta(self) -> None:
        ctx, session, _ = _ctx(AuthenticationError("credenciales"))
        with self.assertRaises(AuthenticationError):
            call(ctx, "Metodo")
        self.assertEqual(session.attempts, 1)

    def test_un_error_de_red_se_reintenta(self) -> None:
        ctx, session, _ = _ctx(CampusError("sin red"), retries=2)
        with mock.patch("autonoma_cli.api.call.time.sleep"):
            with self.assertRaises(CampusError):
                call(ctx, "Metodo")
        self.assertEqual(session.attempts, 2)


class PostRawTests(unittest.TestCase):
    def test_manda_el_cuerpo_y_devuelve_el_texto(self) -> None:
        ctx, session, _ = _ctx(FakeResponse(b"209901_ENTREGA.zip"))

        raw = post_raw(
            ctx, b"--B--\r\n", content_type="multipart/form-data; boundary=B",
            page="/GlobalAplication/FileUpload.ashx",
        )

        self.assertEqual(raw, "209901_ENTREGA.zip")
        request = session.requests[-1]
        self.assertEqual(request.data, b"--B--\r\n")
        self.assertEqual(
            request.get_header("Content-type"), "multipart/form-data; boundary=B"
        )
        self.assertTrue(str(request.full_url).endswith("/GlobalAplication/FileUpload.ashx"))

    def test_un_401_repite_una_sola_vez(self) -> None:
        ctx, session, auth = _ctx(
            CampusHTTPError("401", 401), FakeResponse(b"guardado.zip")
        )

        self.assertEqual(
            post_raw(ctx, b"x", content_type="multipart/form-data; boundary=B", page="/u"),
            "guardado.zip",
        )
        self.assertEqual((auth.expired, auth.relogins, session.attempts), (1, 1, 2))

    def test_un_500_no_se_reintenta(self) -> None:
        ctx, session, _ = _ctx(CampusHTTPError("500", 500))
        with self.assertRaises(CampusHTTPError):
            post_raw(ctx, b"x", content_type="multipart/form-data; boundary=B", page="/u")
        self.assertEqual(session.attempts, 1)

    def test_un_error_de_red_no_se_reintenta(self) -> None:
        ctx, session, _ = _ctx(CampusError("sin red"))
        with self.assertRaises(CampusError):
            post_raw(ctx, b"x", content_type="multipart/form-data; boundary=B", page="/u")
        self.assertEqual(session.attempts, 1)

    def test_una_redireccion_al_login_repite_una_sola_vez(self) -> None:
        ctx, session, auth = _ctx(
            FakeResponse(b"", LOGIN_URL), FakeResponse(b"guardado.zip")
        )

        self.assertEqual(
            post_raw(ctx, b"x", content_type="multipart/form-data; boundary=B", page="/u"),
            "guardado.zip",
        )
        self.assertEqual((auth.expired, auth.relogins, session.attempts), (1, 1, 2))

    def test_sin_credenciales_avisa_como_el_login(self) -> None:
        ctx, _, auth = _ctx(FakeResponse(b"", LOGIN_URL))
        auth.credentials = False
        with self.assertRaises(SessionExpiredError) as raised:
            post_raw(ctx, b"x", content_type="multipart/form-data; boundary=B", page="/u")
        self.assertIn("autonoma login", str(raised.exception))


class PackageTests(unittest.TestCase):
    def test_el_paquete_expone_los_webmethods_sin_importar_el_submodulo(self) -> None:
        code = "from autonoma_cli import api; print(api.methods.get_courses.__name__)"
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "get_courses")


if __name__ == "__main__":
    unittest.main()
