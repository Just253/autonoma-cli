from __future__ import annotations

import unittest

from autonoma_cli.client import CampusClient, unwrap
from autonoma_cli.errors import AuthenticationError, CampusHTTPError
from support.home import IsolatedHomeMixin

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
        client = CampusClient(delay=0)
        responses = [_FakeResponse(client.login_url, LOGIN_HTML), _FakeResponse(final_url, body)]
        client._session.send = lambda request: responses.pop(0)  # type: ignore[method-assign]
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
        client = CampusClient(base_url="https://campus-de-ejemplo.edu", delay=0)
        home = "https://campus-de-ejemplo.edu/Campus/Default.aspx"
        responses = [
            _FakeResponse(client.login_url, LOGIN_HTML),
            _FakeResponse(home, HOME_HTML),
            _FakeResponse(f"{home}/Metodo", '{"d": []}'),
        ]
        seen = []

        def fake_send(request):
            seen.append(request)
            return responses.pop(0)

        client._session.send = fake_send  # type: ignore[method-assign]
        client.login("90000001", "clave-de-ejemplo")

        self.assertEqual(client.student_code, "9000000001")
        self.assertEqual(client.referer, home)

        client._call_once("Metodo", {}, "/Campus/Default.aspx")
        self.assertEqual(seen[-1].get_header("Referer"), home)


class SessionRetryTests(unittest.TestCase):
    def test_http_401_relogs_in_and_retries(self) -> None:
        client = CampusClient(delay=0)
        client._auth._authenticated = True
        calls: list[str] = []
        relogins: list[bool] = []

        def fake_relogin() -> None:
            relogins.append(True)
            client._auth._authenticated = True

        def fake_once(method: str, payload: object, page: str) -> dict[str, bool]:
            calls.append(method)
            if len(calls) == 1:
                raise CampusHTTPError("El campus respondio HTTP 401.", 401)
            return {"ok": True}

        client._auth.relogin = fake_relogin  # type: ignore[method-assign]
        client._call_once = fake_once  # type: ignore[method-assign]

        self.assertEqual(client._call("Alu_ObtenerCursosActuales", {}), {"ok": True})
        self.assertEqual(len(relogins), 1)
        self.assertEqual(len(calls), 2)

    def test_http_500_is_retried(self) -> None:
        client = CampusClient(delay=0, retries=2)
        client._auth._authenticated = True
        calls: list[int] = []

        def fake_once(method: str, payload: object, page: str) -> dict[str, bool]:
            calls.append(1)
            raise CampusHTTPError("El campus respondio HTTP 500.", 500)

        client._call_once = fake_once  # type: ignore[method-assign]
        with self.assertRaises(CampusHTTPError):
            client._call("Alu_ObtenerCursosActuales", {})
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
