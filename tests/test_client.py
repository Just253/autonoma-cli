from __future__ import annotations

import unittest

from autonoma_cli.client import (
    CampusClient,
    LoginPageParser,
    _as_records,
    _extract_student_code,
    unwrap,
)
from autonoma_cli.errors import CampusHTTPError

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


class StudentCodeTests(unittest.TestCase):
    def test_first_pattern(self) -> None:
        html = '<input id="cPerCodigo" value="9000000001" />'
        self.assertEqual(_extract_student_code(html), "9000000001")

    def test_log_input(self) -> None:
        html = '<input id="txtcPerCodigoLog" value="1234567" />'
        self.assertEqual(_extract_student_code(html), "1234567")

    def test_missing(self) -> None:
        self.assertEqual(_extract_student_code("<html></html>"), "")


class HistoryEndpointTests(unittest.TestCase):
    """get_history recorre cada curricula, deduplica y usa las rutas reales."""

    def test_merges_curricula_and_dedupes(self) -> None:
        calls: list[tuple[str, dict, str]] = []

        class Fake(CampusClient):
            def __init__(self) -> None:
                super().__init__(delay=0)

            def ensure_student_code(self) -> str:
                return "9000000001"

            def _call(self, method, payload=None, *, page="/Campus/Default.aspx", allow_relogin=True):
                calls.append((method, dict(payload or {}), page))
                if method == "obtenerUniOrgCurriculo":
                    return [{"nCurCodigo": 1}, {"nCurCodigo": 2}]
                if (payload or {}).get("nCurCodigo") == 1:
                    return {"HISTORIAL_CURSOS": [{"nGruCodigo": 11}, {"nGruCodigo": 12}]}
                return {"HISTORIAL_CURSOS": [{"nGruCodigo": 12}, {"nGruCodigo": 13}]}

        rows = Fake().get_history()
        self.assertEqual([row["nGruCodigo"] for row in rows], [11, 12, 13])
        pages = {page for _, _, page in calls}
        self.assertIn("/Modulos/Campus/MisCursos/Ca_Mc_CursosMatriculados.aspx", pages)
        self.assertIn("/CampusVirtual/ua/Alumno/MisCursos/Alu_HistorialCursos.aspx", pages)


class RecordTests(unittest.TestCase):
    def test_list(self) -> None:
        self.assertEqual(_as_records([{"a": 1}, "x"]), [{"a": 1}])

    def test_wrapped_in_recursos(self) -> None:
        self.assertEqual(_as_records({"recursos": [{"a": 1}]}), [{"a": 1}])

    def test_wrapped_in_d(self) -> None:
        self.assertEqual(_as_records({"d": [{"a": 1}]}), [{"a": 1}])

    def test_unknown_shape(self) -> None:
        self.assertEqual(_as_records("texto"), [])


class SessionRetryTests(unittest.TestCase):
    def test_http_401_relogs_in_and_retries(self) -> None:
        client = CampusClient(delay=0)
        client._authenticated = True
        calls: list[str] = []
        relogins: list[bool] = []

        def fake_relogin() -> None:
            relogins.append(True)
            client._authenticated = True

        def fake_once(method: str, payload: object, page: str) -> dict[str, bool]:
            calls.append(method)
            if len(calls) == 1:
                raise CampusHTTPError("El campus respondio HTTP 401.", 401)
            return {"ok": True}

        client._relogin = fake_relogin  # type: ignore[method-assign]
        client._call_once = fake_once  # type: ignore[method-assign]

        self.assertEqual(client._call("Alu_ObtenerCursosActuales", {}), {"ok": True})
        self.assertEqual(len(relogins), 1)
        self.assertEqual(len(calls), 2)

    def test_http_500_is_retried(self) -> None:
        client = CampusClient(delay=0, retries=2)
        client._authenticated = True
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
