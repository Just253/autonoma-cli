"""Tablas de `autonoma notas`: resumen, detalle, cerrados y filtros."""

from __future__ import annotations

import contextlib
import io
import unittest

from autonoma_cli import ui
from autonoma_cli.commands import run_notas
from support.grades import HISTORY_ROWS, FakeGradesApi, notas_args
from support.home import IsolatedHomeMixin


class NotasCommandTests(IsolatedHomeMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        self.client = FakeGradesApi()

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

    def test_todos_with_curso_is_ignored(self) -> None:
        code, out = self.run_notas(curso="1", todos=True)
        self.assertNotIn("Periodos cerrados", out)

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

    def test_filter_without_matches_says_so(self) -> None:
        code, out = self.run_notas(periodo="209999")
        self.assertEqual(code, 0)
        self.assertIn("Sin cursos que coincidan con el filtro.", out)


if __name__ == "__main__":
    unittest.main()
