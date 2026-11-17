from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest import mock

from autonoma_cli.api import records
from autonoma_cli.api.methods import CourseOverview
from autonoma_cli.client import CampusClient
from autonoma_cli.commands import run_curso
from autonoma_cli.models import Course
from support.home import IsolatedHomeMixin

BASE = "https://campus-de-ejemplo.edu"


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


class CourseOverviewTests(unittest.TestCase):
    """El resumen del curso sale de una sola lectura del detalle."""

    def test_one_request_feeds_syllabus_and_resources(self) -> None:
        calls: list[tuple[str, dict]] = []

        class Fake(CampusClient):
            def __init__(self) -> None:
                super().__init__(base_url=BASE, delay=0)
                self._api = replace(self._api, auth=_student("9000000001"))

            def respond(
                self, ctx, method, payload=None, *, page="/Campus/Default.aspx", **kwargs
            ):
                calls.append((method, dict(payload or {})))
                return {
                    "silabo": [{"nSesion": 1, "tema": "Tema"}],
                    "recursos": [
                        {"cTitulo": "MATERIAL", "nDocLinTipo": 2, "nSesion": 1, "url": "a.pdf"}
                    ],
                }

        client = Fake()
        with mock.patch("autonoma_cli.api.methods.call", client.respond):
            overview = client.course_overview(90000001)

        self.assertEqual([method for method, _ in calls], ["getInformationDetailCurso"])
        self.assertEqual(calls[0][1]["nSesion"], 0)
        self.assertEqual([topic.number for topic in overview.topics], [1])
        self.assertEqual([item.title for item in overview.resources], ["MATERIAL"])
        self.assertEqual(overview.resources[0].url, f"{BASE}/uploads/a.pdf")


class CursoCommandTests(IsolatedHomeMixin, unittest.TestCase):
    """`curso` usa el resumen y no vuelve a pedir silabo ni detalle."""

    def setUp(self) -> None:
        self.make_home()

    def test_curso_usa_el_resumen_sin_repetir_la_lectura(self) -> None:
        class Stub:
            base_url = BASE
            student_code = "2024000001"

            def __init__(self) -> None:
                self.overview_calls = 0
                self.legacy_calls = 0

            def get_courses(self) -> list[Course]:
                return [
                    Course.from_api(
                        {"nGruCodigo": 90000001, "asignatura": "CURSO DE EJEMPLO"}, BASE
                    )
                ]

            def course_overview(self, group_id: object) -> CourseOverview:
                self.overview_calls += 1
                return CourseOverview(topics=[], resources=[])

            def get_syllabus(self, group_id: object) -> list:
                self.legacy_calls += 1
                return []

            def get_course_detail(self, group_id: object, session: int) -> dict:
                self.legacy_calls += 1
                return {}

        stub = Stub()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_curso(stub, argparse.Namespace(curso="90000001", refresh=False, json=True))

        self.assertEqual(code, 0)
        self.assertEqual(stub.overview_calls, 1)
        self.assertEqual(stub.legacy_calls, 0, "no se repite la lectura del detalle")
        self.assertEqual(json.loads(output.getvalue())["course"]["group_id"], 90000001)


if __name__ == "__main__":
    unittest.main()
