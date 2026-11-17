from __future__ import annotations

import tempfile
import unittest
from http.cookiejar import Cookie, LWPCookieJar
from pathlib import Path
from typing import Any

from autonoma_cli.auth.session import AuthSession
from autonoma_cli.errors import AuthenticationError, SessionExpiredError

LOGIN_HTML = """
<form name="frmLogin" method="post" action="./Login.aspx" id="frmLogin">
  <input type="hidden" name="__VIEWSTATE" value="AAA" />
  <input name="txtUsuario" type="text" />
  <input name="txtPassword" type="password" />
  <input type="submit" name="btn_ingresar" value="Ingresar" />
</form>
"""

HOME_HTML = '<html><body><input id="cPerCodigo" value="9000000001" /></body></html>'
LOGIN_URL = "https://campus-de-ejemplo.edu/Campus/Login.aspx"
HOME_URL = "https://campus-de-ejemplo.edu/Campus/Default.aspx"


def _cookie(name: str = "ASP.NET_SessionId", value: str = "abc") -> Cookie:
    return Cookie(
        version=0, name=name, value=value, port=None,
        port_specified=False, domain="campus-de-ejemplo.edu", domain_specified=True,
        domain_initial_dot=False, path="/", path_specified=True, secure=False,
        expires=None, discard=False, comment=None, comment_url=None, rest={},
    )


class _FakeResponse:
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


class _Transport:
    """Transporte guionado: respuestas en orden y sin red."""

    def __init__(self, path: str, *responses: _FakeResponse) -> None:
        self.home_url = HOME_URL
        self.cookies_path = path
        self.jar = LWPCookieJar(path)
        self.responses = list(responses)
        self.requests: list[Any] = []

    def send(self, request: Any, *, cookies: bool = True) -> _FakeResponse:
        self.requests.append(request)
        return self.responses.pop(0)


class _Store:
    """Archivo del codigo de alumno en memoria."""

    def __init__(self, code: str = "") -> None:
        self.code = code
        self.saves: list[str] = []

    def load(self) -> str:
        return self.code

    def save(self, code: str) -> None:
        self.code = code
        self.saves.append(code)


class AuthSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "config" / "session.cookies")

    def _session(
        self, *responses: _FakeResponse, student: _Store | None = None
    ) -> tuple[AuthSession, _Transport]:
        transport = _Transport(self.path, *responses)
        session = AuthSession(
            transport, LOGIN_URL, {"User-Agent": "test"}, student=student
        )
        return session, transport

    def _login(self, final_url: str = HOME_URL, body: str = HOME_HTML) -> tuple[AuthSession, _Transport]:
        session, transport = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(final_url, body),
        )
        session.login("90000001", "clave-de-ejemplo")
        return session, transport

    def test_starts_closed_and_without_a_code(self) -> None:
        session, _ = self._session()
        self.assertFalse(session.authenticated)
        self.assertEqual(session.student_code, "")

    def test_login_marks_the_session_and_reads_the_code(self) -> None:
        session, transport = self._login()
        self.assertTrue(session.authenticated)
        self.assertEqual(session.student_code, "9000000001")
        self.assertEqual(transport.home_url, HOME_URL)
        self.assertTrue(Path(self.path).exists())

    def test_login_posts_the_hidden_fields_and_the_credentials(self) -> None:
        _, transport = self._login()
        self.assertEqual(transport.requests[0].full_url, LOGIN_URL)
        body = transport.requests[1].data.decode("utf-8")
        self.assertIn("__VIEWSTATE=AAA", body)
        self.assertIn("txtUsuario=90000001", body)
        self.assertIn("btn_ingresar=Ingresar", body)
        self.assertEqual(transport.requests[1].get_header("Referer"), LOGIN_URL)

    def test_login_rejects_with_the_campus_message(self) -> None:
        body = '<span id="FailureText">La clave es incorrecta.</span>'
        session, _ = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(f"{LOGIN_URL}?ReturnUrl=%2f", body),
        )
        with self.assertRaises(AuthenticationError) as ctx:
            session.login("90000001", "otra")
        self.assertIn("La clave es incorrecta.", str(ctx.exception))
        self.assertFalse(session.authenticated)

    def test_login_reports_the_forced_password_change(self) -> None:
        session, _ = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse("https://campus-de-ejemplo.edu/Campus/CambioContrasena.aspx", ""),
        )
        with self.assertRaises(AuthenticationError) as ctx:
            session.login("90000001", "clave-de-ejemplo")
        self.assertIn("exige cambiarla", str(ctx.exception))

    def test_login_warns_about_captcha_on_an_unknown_page(self) -> None:
        session, _ = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse("https://campus-de-ejemplo.edu/Campus/Otra.aspx", ""),
        )
        with self.assertRaises(AuthenticationError) as ctx:
            session.login("90000001", "clave-de-ejemplo")
        self.assertIn("CAPTCHA", str(ctx.exception))

    def test_login_requires_both_fields(self) -> None:
        session, _ = self._session()
        with self.assertRaises(AuthenticationError) as ctx:
            session.login(" ", "clave-de-ejemplo")
        self.assertEqual(str(ctx.exception), "Usuario y contrasena son obligatorios.")

    def test_authenticate_reuses_a_saved_cookie(self) -> None:
        jar = LWPCookieJar(self.path)
        jar.set_cookie(_cookie())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        jar.save(ignore_discard=True, ignore_expires=True)

        session, transport = self._session()
        self.assertFalse(session.authenticate("90000001", "clave-de-ejemplo"))
        self.assertTrue(session.authenticated)
        self.assertEqual(transport.requests, [])

    def test_authenticate_with_force_login_posts_the_form(self) -> None:
        session, transport = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(HOME_URL, HOME_HTML),
        )
        self.assertTrue(
            session.authenticate("90000001", "clave-de-ejemplo", force_login=True)
        )
        self.assertEqual(len(transport.requests), 2)

    def test_relogin_without_credentials_explains_the_next_step(self) -> None:
        session, _ = self._session()
        with self.assertRaises(SessionExpiredError) as ctx:
            session.relogin()
        self.assertEqual(
            str(ctx.exception),
            "La sesion del campus expiro y no hay credenciales para renovarla. "
            "Ejecuta: autonoma login",
        )

    def test_relogin_repeats_the_last_login(self) -> None:
        session, transport = self._login()
        transport.responses = [
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(HOME_URL, HOME_HTML),
        ]
        session.expire()
        session.relogin()
        self.assertTrue(session.authenticated)
        self.assertEqual(len(transport.requests), 4)

    def test_logout_removes_the_cookie_and_the_state(self) -> None:
        session, _ = self._login()
        self.assertTrue(session.logout())
        self.assertFalse(session.authenticated)
        self.assertEqual(session.student_code, "")
        self.assertFalse(Path(self.path).exists())
        self.assertFalse(session.logout())

    def test_cookie_header_reads_the_jar(self) -> None:
        session, transport = self._login()
        transport.jar.set_cookie(_cookie())
        self.assertEqual(session.cookie_header(), "ASP.NET_SessionId=abc")

    def test_cookie_names_lists_the_jar_without_values(self) -> None:
        session, transport = self._login()
        transport.jar.set_cookie(_cookie())
        self.assertEqual(session.cookie_names(), ["ASP.NET_SessionId"])

    def test_ensure_student_code_reads_the_panel_once(self) -> None:
        session, transport = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(HOME_URL, '<html><body>sin codigo</body></html>'),
            _FakeResponse(HOME_URL, HOME_HTML),
        )
        session.login("90000001", "clave-de-ejemplo")
        self.assertEqual(session.student_code, "")
        self.assertEqual(session.ensure_student_code(), "9000000001")
        self.assertEqual(session.ensure_student_code(), "9000000001")
        self.assertEqual(len(transport.requests), 3)

    def test_expire_closes_the_session_without_touching_the_cookie(self) -> None:
        session, _ = self._login()
        session.expire()
        self.assertFalse(session.authenticated)
        self.assertEqual(session.student_code, "9000000001")
        self.assertTrue(Path(self.path).exists())

    def test_starts_with_the_saved_code_and_skips_the_panel(self) -> None:
        store = _Store("9000000001")
        session, transport = self._session(student=store)
        self.assertEqual(session.student_code, "9000000001")
        self.assertEqual(session.ensure_student_code(), "9000000001")
        self.assertEqual(transport.requests, [])

    def test_ensure_student_code_uses_the_saved_code_first(self) -> None:
        """Sin tocar ``student_code`` antes: el atajo tiene que servir igual."""

        store = _Store("9000000001")
        session, transport = self._session(student=store)
        self.assertEqual(session.ensure_student_code(), "9000000001")
        self.assertEqual(transport.requests, [])

    def test_login_persists_the_code(self) -> None:
        store = _Store()
        session, _ = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(HOME_URL, HOME_HTML),
            student=store,
        )
        session.login("90000001", "clave-de-ejemplo")
        self.assertEqual(store.code, "9000000001")

    def test_ensure_student_code_persists_what_it_reads(self) -> None:
        store = _Store()
        session, _ = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(HOME_URL, '<html><body>sin codigo</body></html>'),
            _FakeResponse(HOME_URL, HOME_HTML),
            student=store,
        )
        session.login("90000001", "clave-de-ejemplo")
        self.assertEqual(store.code, "")
        self.assertEqual(session.ensure_student_code(), "9000000001")
        self.assertEqual(store.code, "9000000001")

    def test_login_sin_codigo_borra_el_guardado(self) -> None:
        """Un login que no trae codigo no puede dejar el de la cuenta anterior."""

        store = _Store("9000000001")
        session, _ = self._session(
            _FakeResponse(LOGIN_URL, LOGIN_HTML),
            _FakeResponse(HOME_URL, '<html><body>sin codigo</body></html>'),
            student=store,
        )
        session.login("90000001", "clave-de-ejemplo")
        self.assertEqual(store.code, "")

    def test_logout_clears_the_saved_code(self) -> None:
        store = _Store("9000000001")
        session, _ = self._session(student=store)
        session.logout()
        self.assertEqual(store.code, "")


if __name__ == "__main__":
    unittest.main()
