"""Tests de `autonoma notas`: comando, tablas y los cuatro casos de JSON."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from autonoma_cli import ui
from autonoma_cli.cli import main
from autonoma_cli.commands import run_notas
from autonoma_cli.models import AcademicSummary, Course, CourseGrades

BASE = "https://virtual.autonoma.edu.pe"


def courses() -> list[Course]:
    return [
        Course.from_api(
            {
                "nGruCodigo": 90000001,
                "asignatura": "CURSO DE EJEMPLO UNO",
                "codigo": "PISOP00001",
                "periodo": "209901",
                "ciclo": "8",
                "grupo": "1T1",
                "creditos": "3",
                "EstadoCurso": "1",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000002,
                "asignatura": "CURSO DE EJEMPLO DOS",
                "codigo": "PISOP00002",
                "periodo": "209901",
                "ciclo": "8",
                "grupo": "1T1",
                "creditos": "4",
                "EstadoCurso": "1",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000003,
                "asignatura": "CURSO DE EJEMPLO TRES",
                "codigo": "PISOP00003",
                "periodo": "209901",
                "ciclo": "8",
                "grupo": "1T1",
                "creditos": "3",
                "EstadoCurso": "2",
            },
            BASE,
        ),
    ]


HISTORY_ROWS = [
    {
        "nGruCodigo": 90000011,
        "asignatura": "CURSO HISTORICO UNO",
        "cCodigoAsignatura": "EJEM0001",
        "cPeriodo": "209802",
        "nCiclo": 7,
        "cEstado": "APROBADA",
        "cTipo": "MATRICULA REGULAR",
        "carrera": "INGENIERÍA DE EJEMPLO",
        "Grupo": "1T1",
        "nNroCredito": 3,
        "docente": "DOCENTE DE EJEMPLO",
        "nPromocional": 15,
    },
    {
        # Mismo grupo que el catalogo activo: no debe repetirse en el historico.
        "nGruCodigo": 90000001,
        "asignatura": "CURSO DE EJEMPLO UNO",
        "cPeriodo": "209901",
        "nCiclo": 8,
        "cEstado": "EN PROCESO",
        "nNroCredito": 3,
        "nPromocional": 9,
    },
]

GRADES_RAW = {
    "90000001": {
        "fechaActualizado": "02/11/2027 20:30:30",
        "nPromTotal": "9.6",
        "porcentaje": "67",
        "notas": [
            {"Criterio": "EC", "Peso": "10", "nota": "20.00", "nSesion": 4,
             "cFechaInicio": "25/09/2027", "cFechaFin": "27/09/2027"},
            {"Criterio": "EP", "Peso": "40", "nota": "19.00", "nSesion": 8,
             "cFechaInicio": "23/10/2027", "cFechaFin": "25/10/2027"},
            {"Criterio": "EF", "Peso": "50", "nota": "-", "nSesion": 16,
             "cFechaInicio": "18/12/2027", "cFechaFin": "19/12/2027"},
        ],
    },
    "90000002": {
        "fechaActualizado": "02/11/2027 20:30:30",
        "nPromTotal": "0",
        "porcentaje": "0",
        "notas": [],
    },
}

SUMMARY_RAW = {
    "Malla_Curricular": [
        {"Nota": 16, "nNroCredito": 3, "nPromedioAcumulado": 15.23, "perMerito": 12},
        {"Nota": 14, "nNroCredito": 4, "nPromedioAcumulado": 15.23, "perMerito": 12},
        {"Nota": 0, "nNroCredito": 3, "nPromedioAcumulado": 15.23, "perMerito": 12},
    ],
    "Malla_Curricular_grafAvanceCarrera": [
        {"totalCreditos": 135, "totalCreditosAprobados": 120},
    ],
    "Malla_Curricular_grafPromedioNotaByCiclo": [
        {"Periodo": "209801", "promedioPorCiclo": 14.5},
        {"Periodo": "209802", "promedioPorCiclo": 15.75},
    ],
}


class FakeGradesClient:
    """Cliente de mentira: mismas firmas que usa run_notas, sin red."""

    base_url = BASE
    student_code = "2024000001"

    def __init__(self) -> None:
        self.grade_calls: list[str] = []
        self.summary_calls = 0

    def get_courses(self) -> list[Course]:
        return courses()

    def get_history(self) -> list[dict[str, object]]:
        return [dict(row) for row in HISTORY_ROWS]

    def get_grades(self, group_id: int | str) -> CourseGrades:
        self.grade_calls.append(str(group_id))
        raw = GRADES_RAW.get(str(group_id), {"notas": []})
        return CourseGrades.from_api(raw, group_id=group_id)

    def get_academic_summary(self) -> AcademicSummary:
        self.summary_calls += 1
        return AcademicSummary.from_api(SUMMARY_RAW)


def notas_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "curso": None,
        "todos": False,
        "activos": False,
        "periodo": None,
        "ciclo": None,
        "carrera": None,
        "promedio": False,
        "refresh": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class IsolatedHomeMixin:
    """AUTONOMA_CLI_HOME a una carpeta temporal: ni lee ni escribe la cache real."""

    tmp: tempfile.TemporaryDirectory[str]

    def make_home(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"AUTONOMA_CLI_HOME": self.tmp.name}, clear=False)
        env.start()
        self.addCleanup(env.stop)


class NotasCommandTests(IsolatedHomeMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        self.client = FakeGradesClient()

    def run_notas(self, **overrides: object) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_notas(self.client, notas_args(**overrides))
        return code, output.getvalue()

    def test_summary_lists_active_courses(self) -> None:
        code, out = self.run_notas()
        self.assertEqual(code, 0)
        self.assertIn("Curso", out)
        self.assertIn("Acumulado", out)
        self.assertIn("CURSO DE EJEMPLO UNO", out)
        self.assertIn("9.6", out)
        self.assertIn("67%", out)
        self.assertNotIn("CURSO HISTORICO UNO", out)
        self.assertNotIn("CURSO DE EJEMPLO TRES", out)  # inactivo: fuera del resumen
        self.assertEqual(self.client.grade_calls, ["90000001", "90000002"])

    def test_detail_shows_every_criterion(self) -> None:
        code, out = self.run_notas(curso="1")
        self.assertEqual(code, 0)
        self.assertIn("CURSO DE EJEMPLO UNO", out)
        self.assertIn("periodo 209901", out)
        for expected in ("Criterio", "EC", "20.00", "EP", "19.00", "EF", "18/12/2027"):
            self.assertIn(expected, out)
        self.assertIn("Acumulado 9.6 / 20 (solo 67 % evaluado)", out)
        self.assertIn("Actualizado 02/11/2027 20:30:30", out)

    def test_course_without_criteria_says_so(self) -> None:
        code, out = self.run_notas(curso="2")
        self.assertEqual(code, 0)
        self.assertIn("Sin criterios de evaluacion todavia.", out)
        self.assertNotIn("Acumulado 0", out)

    def test_todos_adds_closed_section_and_deduplicates(self) -> None:
        code, out = self.run_notas(todos=True)
        self.assertEqual(code, 0)
        self.assertIn("Periodos cerrados", out)
        self.assertIn("CURSO HISTORICO UNO", out)
        self.assertIn("209802", out)
        self.assertIn("15", out)
        # El grupo activo no se repite como cerrado.
        self.assertEqual(out.count("CURSO DE EJEMPLO UNO"), 1)

    def test_todos_without_closed_courses_is_not_an_error(self) -> None:
        self.client.get_history = lambda: []  # type: ignore[method-assign]
        code, out = self.run_notas(todos=True)
        self.assertEqual(code, 0)
        self.assertIn("Sin cursos cerrados fuera del periodo activo.", out)

    def test_single_closed_course_uses_npromocional(self) -> None:
        code, out = self.run_notas(curso="90000011")
        self.assertEqual(code, 0)
        self.assertIn("CURSO HISTORICO UNO", out)
        self.assertIn("Nota final: 15", out)
        self.assertNotIn("Sin criterios", out)

    def test_closed_course_does_not_request_grades(self) -> None:
        self.run_notas(curso="90000011")
        self.assertNotIn("90000011", self.client.grade_calls)

    def test_closed_course_without_grade_still_reports_final(self) -> None:
        self.client.get_history = lambda: [  # type: ignore[method-assign]
            {**HISTORY_ROWS[0], "nGruCodigo": 90000012, "nPromocional": ""}
        ]
        code, out = self.run_notas(curso="90000012")
        self.assertEqual(code, 0)
        self.assertIn("Nota final: -", out)
        self.assertNotIn("Sin criterios", out)

    def test_json_closed_course_without_grade(self) -> None:
        self.client.get_history = lambda: [  # type: ignore[method-assign]
            {**HISTORY_ROWS[0], "nGruCodigo": 90000012, "nPromocional": ""}
        ]
        code, out = self.run_notas(curso="90000012", json=True)
        payload = json.loads(out)
        self.assertTrue(payload["closed"])
        self.assertIsNone(payload["grade_value"])
        self.assertEqual(payload["grade"], "")

    def test_json_promedio_for_closed_course(self) -> None:
        code, out = self.run_notas(curso="90000011", promedio=True, json=True)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"course", "official"})
        self.assertTrue(payload["course"]["closed"])

    def test_json_empty_summary_is_an_empty_list(self) -> None:
        code, out = self.run_notas(periodo="209999", json=True)
        self.assertEqual(json.loads(out), [])

    def test_todos_with_curso_is_ignored(self) -> None:
        code, out = self.run_notas(curso="1", todos=True)
        self.assertNotIn("Periodos cerrados", out)

    def test_json_summary(self) -> None:
        code, out = self.run_notas(json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(len(payload), 2)
        self.assertEqual(set(payload[0]), {
            "group_id", "course", "period", "cycle",
            "average", "average_value", "percent", "updated",
        })
        self.assertEqual(payload[0]["group_id"], 90000001)
        self.assertEqual(payload[0]["course"], "CURSO DE EJEMPLO UNO")
        self.assertEqual(payload[0]["average_value"], 9.6)
        self.assertEqual(payload[1]["average_value"], 0.0)

    def test_json_detail(self) -> None:
        code, out = self.run_notas(curso="1", json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["group_id"], 90000001)
        self.assertEqual(len(payload["items"]), 3)
        self.assertEqual(set(payload["items"][0]), {
            "criterion", "weight", "grade", "grade_value", "session", "from", "to",
        })
        self.assertEqual(payload["items"][0]["session"], 4)
        self.assertEqual(payload["items"][0]["from"], "25/09/2027")
        self.assertIsNone(payload["items"][2]["grade_value"])

    def test_json_todos(self) -> None:
        code, out = self.run_notas(todos=True, json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"courses", "closed"})
        self.assertEqual(len(payload["courses"]), 2)
        self.assertEqual(len(payload["closed"]), 1)
        closed = payload["closed"][0]
        self.assertEqual(set(closed), {
            "group_id", "course", "period", "cycle", "grade", "grade_value", "closed",
        })
        self.assertEqual(closed["group_id"], 90000011)
        self.assertEqual(closed["grade"], "15")
        self.assertEqual(closed["grade_value"], 15.0)
        self.assertTrue(closed["closed"])

    def test_json_cerrado_suelto(self) -> None:
        code, out = self.run_notas(curso="90000011", json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {
            "group_id", "course", "period", "cycle", "grade", "grade_value", "closed",
        })
        self.assertTrue(payload["closed"])
        self.assertEqual(payload["grade_value"], 15.0)

    def test_promedio_block(self) -> None:
        code, out = self.run_notas(promedio=True)
        self.assertEqual(code, 0)
        self.assertIn("Promedio oficial", out)
        self.assertIn("Acumulado del tablero", out)
        self.assertIn("15.23", out)
        self.assertIn("Calculado por creditos", out)
        self.assertIn("14.86 (7 creditos)", out)
        self.assertIn("120 de 135 aprobados", out)
        self.assertIn("Promedio 209801", out)
        self.assertEqual(self.client.summary_calls, 1)

    def test_json_promedio(self) -> None:
        code, out = self.run_notas(promedio=True, json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"courses", "official"})
        official = payload["official"]
        self.assertEqual(official["accumulated"], 15.23)
        self.assertEqual(official["weighted"], 14.86)
        self.assertEqual(official["credits_weighted"], 7.0)
        self.assertEqual([cycle["period"] for cycle in official["cycles"]],
                         ["209801", "209802"])

    def test_json_promedio_for_one_course(self) -> None:
        code, out = self.run_notas(curso="1", promedio=True, json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"course", "official"})
        self.assertEqual(payload["course"]["group_id"], 90000001)

    def test_filter_without_matches_says_so(self) -> None:
        code, out = self.run_notas(periodo="209999")
        self.assertEqual(code, 0)
        self.assertIn("Sin cursos que coincidan con el filtro.", out)


class NotasMainTests(IsolatedHomeMixin, unittest.TestCase):
    """`autonoma notas --json` de punta a punta con el parser real."""

    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        patcher = mock.patch(
            "autonoma_cli.commands.client_for", return_value=FakeGradesClient()
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(argv))
        return code, output.getvalue()

    def test_main_notas_json(self) -> None:
        code, out = self.run_main("notas", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)), 2)

    def test_main_notas_todos_promedio(self) -> None:
        code, out = self.run_main("notas", "--todos", "--promedio", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"courses", "closed", "official"})


if __name__ == "__main__":
    unittest.main()
