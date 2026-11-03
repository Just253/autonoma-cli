from __future__ import annotations

import unittest

from autonoma_cli.client import CampusClient, _as_records


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


if __name__ == "__main__":
    unittest.main()
