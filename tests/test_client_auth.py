from __future__ import annotations

import unittest
from unittest import mock

from autonoma_cli.api import unwrap
from autonoma_cli.client import CampusClient
from autonoma_cli.errors import AuthenticationError, CampusHTTPError
from support.home import IsolatedHomeMixin
from support.session import FakeSession, save_cookie

BASE = "https://campus-de-ejemplo.edu"
LOGIN_URL = f"{BASE}/Campus/Login.aspx"
HOME_URL = f"{BASE}/Campus/Default.aspx"

LOGIN_HTML = """
<form name="frmLogin" method="post" action="./Login.aspx" id="frmLogin">
  <input type="hidden" name="__EVENTTARGET" value="" />
  <input type="hidden" name="__VIEWSTATE" value="AAA" />
  <input type="hidden" name="__EVENTVALIDATION" value="BBB" />
  <input type="hidden" name="__VIEWSTATEGENERATOR" value="CCC" />
  <input name="txtUsuario" id="txtUsuario" type="text" name="email-username" />
  <input name="txtPassword" type="password" id="txtPassword" name="password" />
  <input type="submit" name="btn_ingresar" value="Ingresar" id="btn_ingresar" />
</form>
"""

HOME_HTML = '<html><body><input id="cPerCodigo" value="9000000001" /></body></html>'


class _FakeResponse:
    """Respuesta minima de ``send`` para probar ``login`` sin red."""

    def __init__(self, url: str, body: str) -> None:
        self._url = url
        self._body = body.encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def geturl(self) -> str:
        return self._url

    def read(self) -> bytes:
        return self._body


class UnwrapTests(unittest.TestCase):
    def test_plain_dictionary(self) -> None:
        self.assertEqual(unwrap({"a": 1}), {"a": 1})

    def test_d_key_dictionary(self) -> None:
        self.assertEqual(unwrap({"d": {"a": 1}}), {"a": 1})

    def test_d_key_json_string(self) -> None:
        self.assertEqual(unwrap({"d": '[{"a": 1}]'}), [{"a": 1}])

    def test_d_key_plain_string(self) -> None:
        self.assertEqual(unwrap({"d": "hola"}), "hola")

    def test_none(self) -> None:
        self.assertIsNone(unwrap(None))


class LoginRedirectTests(unittest.TestCase):
    """El login distingue el cambio obligatorio de contrasena de un fallo real."""

    def _login(self, final_url: str, body: str = "") -> None:
        session = FakeSession()
        client = CampusClient(delay=0, session=session)
        session.responses = [
            _FakeResponse(client.login_url, LOGIN_HTML),
            _FakeResponse(final_url, body),
        ]
        client.login("90000001", "clave-de-ejemplo")

    def test_cambio_obligatorio_de_contrasena_se_informa(self) -> None:
        # El campus autentica y luego manda a CambioContrasena.aspx: no es CAPTCHA.
        with self.assertRaises(AuthenticationError) as ctx:
            self._login("https://campus-de-ejemplo.edu/Campus/CambioContrasena.aspx?r=0")
        self.assertIn("exige cambiarla", str(ctx.exception))

    def test_pagina_inesperada_sigue_avisando_captcha(self) -> None:
        with self.assertRaises(AuthenticationError) as ctx:
            self._login("https://campus-de-ejemplo.edu/Campus/Otra.aspx")
        self.assertIn("CAPTCHA", str(ctx.exception))


class HomeUrlTests(IsolatedHomeMixin, unittest.TestCase):
    """El login fija el referer que usan las llamadas siguientes."""

    def setUp(self) -> None:
        self.make_home()

    def test_login_actualiza_el_referer_de_las_llamadas(self) -> None:
        session = FakeSession()
        client = CampusClient(base_url=BASE, delay=0, session=session)
        session.responses = [
            _FakeResponse(client.login_url, LOGIN_HTML),
            _FakeResponse(HOME_URL, HOME_HTML),
            _FakeResponse(f"{HOME_URL}/Metodo", '{"d": []}'),
        ]
        client.login("90000001", "clave-de-ejemplo")

        self.assertEqual(client.student_code, "9000000001")
        self.assertEqual(client.referer, HOME_URL)

        client.call("Metodo", {})
        self.assertEqual(session.requests[-1].get_header("Referer"), HOME_URL)


def _authenticated(
    *responses: object, retries: int = 3
) -> tuple[CampusClient, FakeSession]:
    """Cliente con cookie guardada: queda autenticado sin pedir el login."""

    session = FakeSession(*responses)
    save_cookie(session)
    client = CampusClient(delay=0, retries=retries, session=session)
    client.authenticate("90000001", "clave-de-ejemplo")
    return client, session


class SessionRetryTests(unittest.TestCase):
    def test_http_401_relogs_in_and_retries(self) -> None:
        client, session = _authenticated(
            CampusHTTPError("El campus respondio HTTP 401.", 401),
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(HOME_URL, HOME_HTML),
            _FakeResponse(f"{HOME_URL}/Alu_ObtenerCursosActuales", '{"d": {"ok": true}}'),
        )

        self.assertEqual(client.call("Alu_ObtenerCursosActuales", {}), {"ok": True})
        self.assertEqual(session.attempts, 4)
        self.assertTrue(client.authenticated)

    def test_http_500_is_retried(self) -> None:
        client, session = _authenticated(
            CampusHTTPError("El campus respondio HTTP 500.", 500), retries=2
        )

        with mock.patch("autonoma_cli.api.call.time.sleep"):
            with self.assertRaises(CampusHTTPError):
                client.call("Alu_ObtenerCursosActuales", {})

        self.assertEqual(session.attempts, 2)


if __name__ == "__main__":
    unittest.main()
