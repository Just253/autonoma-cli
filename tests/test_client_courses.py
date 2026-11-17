from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from autonoma_cli.api import records
from autonoma_cli.client import CampusClient


def _student(code: str) -> SimpleNamespace:
    """Auth minima: el codigo de alumno ya conocido, sin red."""

    return SimpleNamespace(ensure_student_code=lambda: code)


class HistoryEndpointTests(unittest.TestCase):
    """get_history recorre cada curricula, deduplica y usa las rutas reales."""

    def test_merges_curricula_and_dedupes(self) -> None:
        calls: list[tuple[str, dict, str]] = []

        class Fake(CampusClient):
            def __init__(self) -> None:
                super().__init__(delay=0)
                self._api = replace(self._api, auth=_student("9000000001"))

            def respond(
                self, ctx, method, payload=None, *, page="/Campus/Default.aspx", **kwargs
            ):
                calls.append((method, dict(payload or {}), page))
                if method == "obtenerUniOrgCurriculo":
                    return [{"nCurCodigo": 1}, {"nCurCodigo": 2}]
                if (payload or {}).get("nCurCodigo") == 1:
                    return {"HISTORIAL_CURSOS": [{"nGruCodigo": 11}, {"nGruCodigo": 12}]}
                return {"HISTORIAL_CURSOS": [{"nGruCodigo": 12}, {"nGruCodigo": 13}]}

        client = Fake()
        with mock.patch("autonoma_cli.api.methods.call", client.respond):
            rows = client.get_history()
        self.assertEqual([row["nGruCodigo"] for row in rows], [11, 12, 13])
        pages = {page for _, _, page in calls}
        self.assertIn("/Modulos/Campus/MisCursos/Ca_Mc_CursosMatriculados.aspx", pages)
        self.assertIn("/CampusVirtual/ua/Alumno/MisCursos/Alu_HistorialCursos.aspx", pages)


class RecordTests(unittest.TestCase):
    def test_list(self) -> None:
        self.assertEqual(records([{"a": 1}, "x"]), [{"a": 1}])

    def test_wrapped_in_recursos(self) -> None:
        self.assertEqual(records({"recursos": [{"a": 1}]}), [{"a": 1}])

    def test_wrapped_in_d(self) -> None:
        self.assertEqual(records({"d": [{"a": 1}]}), [{"a": 1}])

    def test_unknown_shape(self) -> None:
        self.assertEqual(records("texto"), [])


if __name__ == "__main__":
    unittest.main()
