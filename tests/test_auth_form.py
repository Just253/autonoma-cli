from __future__ import annotations

import unittest

from autonoma_cli.auth.form import (
    LOGIN_REDIRECT,
    LoginOutcome,
    LoginPageParser,
    build_login_data,
    classify_login,
    student_code_from_html,
)

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


class LoginParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = LoginPageParser()
        self.parser.feed(LOGIN_HTML)

    def test_action(self) -> None:
        self.assertEqual(self.parser.action, "./Login.aspx")

    def test_hidden_fields(self) -> None:
        self.assertEqual(self.parser.hidden["__VIEWSTATE"], "AAA")
        self.assertEqual(self.parser.hidden["__EVENTVALIDATION"], "BBB")
        self.assertIn("__EVENTTARGET", self.parser.hidden)

    def test_submit(self) -> None:
        self.assertEqual(self.parser.submit["btn_ingresar"], "Ingresar")

    def test_duplicate_name_attr_takes_first(self) -> None:
        # El HTML real repite name= en los inputs; el parser debe conservar el primero.
        self.assertNotIn("email-username", self.parser.hidden)
        self.assertNotIn("email-username", self.parser.submit)


class LoginDataTests(unittest.TestCase):
    def _data(self, html: str) -> dict[str, str]:
        parser = LoginPageParser()
        parser.feed(html)
        return build_login_data(parser, "90000001", "clave-de-ejemplo")

    def test_keeps_hidden_fields_and_adds_credentials(self) -> None:
        data = self._data(LOGIN_HTML)
        self.assertEqual(data["__VIEWSTATE"], "AAA")
        self.assertEqual(data["txtUsuario"], "90000001")
        self.assertEqual(data["txtPassword"], "clave-de-ejemplo")
        self.assertEqual(data["btn_ingresar"], "Ingresar")

    def test_uses_the_first_submit_when_the_named_one_is_missing(self) -> None:
        html = (
            '<form action="./Login.aspx"><input type="hidden" name="__VIEWSTATE" value="AAA" />'
            '<input type="submit" name="otro" value="Entrar" /></form>'
        )
        data = self._data(html)
        self.assertEqual(data["otro"], "Entrar")
        self.assertNotIn("btn_ingresar", data)

    def test_falls_back_to_the_default_button(self) -> None:
        html = '<form action="./Login.aspx"><input type="hidden" name="__VIEWSTATE" value="AAA" /></form>'
        data = self._data(html)
        self.assertEqual(data["btn_ingresar"], "Ingresar")


class StudentCodeTests(unittest.TestCase):
    def test_first_pattern(self) -> None:
        html = '<input id="cPerCodigo" value="9000000001" />'
        self.assertEqual(student_code_from_html(html), "9000000001")

    def test_log_input(self) -> None:
        html = '<input id="txtcPerCodigoLog" value="1234567" />'
        self.assertEqual(student_code_from_html(html), "1234567")

    def test_missing(self) -> None:
        self.assertEqual(student_code_from_html("<html></html>"), "")


class ClassifyLoginTests(unittest.TestCase):
    def test_redirect_marks_the_credentials_as_rejected(self) -> None:
        body = '<span id="FailureText" class="error">La clave es incorrecta.</span>'
        outcome = classify_login("https://campus-de-ejemplo.edu/Campus/Login.aspx", body)
        self.assertEqual(outcome, LoginOutcome(LoginOutcome.REJECTED, "La clave es incorrecta."))

    def test_rejection_without_a_campus_message_has_no_detail(self) -> None:
        outcome = classify_login("https://campus-de-ejemplo.edu/Campus/Login.aspx?x=1", "")
        self.assertEqual(outcome.kind, LoginOutcome.REJECTED)
        self.assertEqual(outcome.detail, "")

    def test_forced_password_change(self) -> None:
        outcome = classify_login(
            "https://campus-de-ejemplo.edu/Campus/CambioContrasena.aspx?r=0", ""
        )
        self.assertEqual(outcome.kind, LoginOutcome.PASSWORD_CHANGE)

    def test_unknown_page_is_unexpected(self) -> None:
        outcome = classify_login("https://campus-de-ejemplo.edu/Campus/Otra.aspx", "")
        self.assertEqual(outcome.kind, LoginOutcome.UNEXPECTED)

    def test_panel_page_is_ok(self) -> None:
        self.assertEqual(
            classify_login("https://campus-de-ejemplo.edu/Campus/Default.aspx", "").kind,
            LoginOutcome.OK,
        )

    def test_student_code_in_the_body_is_ok(self) -> None:
        body = '<input id="cPerCodigo" value="9000000001" />'
        self.assertEqual(
            classify_login("https://campus-de-ejemplo.edu/Campus/Otra.aspx", body).kind,
            LoginOutcome.OK,
        )

    def test_login_redirect_matches_the_login_page_only(self) -> None:
        self.assertTrue(LOGIN_REDIRECT.search("https://x.edu/Campus/Login.aspx?ReturnUrl=%2f"))
        self.assertFalse(LOGIN_REDIRECT.search("https://x.edu/Campus/Default.aspx"))


if __name__ == "__main__":
    unittest.main()
