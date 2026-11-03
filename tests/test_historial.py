from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from autonoma_cli import ui
from autonoma_cli.cli import main
from autonoma_cli.commands.data import resolve_any
from autonoma_cli.errors import UsageError
from autonoma_cli.models import HistoryCourse
from support import FakeHistoryClient, IsolatedHomeMixin, courses
from support.fakes import HISTORY_ROWS


class HistoryModelTests(unittest.TestCase):
    def test_maps_the_historial_row(self) -> None:
        course = HistoryCourse.from_api(HISTORY_ROWS[0])
        self.assertEqual(course.period, "209802")
        self.assertEqual(course.cycle, "7")
        self.assertEqual(course.state, "APROBADA")
        self.assertEqual(course.career, "INGENIERÍA DE EJEMPLO")

    def test_to_course_marks_finished_courses_inactive(self) -> None:
        old = HistoryCourse.from_api(HISTORY_ROWS[0]).to_course()
        current = HistoryCourse.from_api(HISTORY_ROWS[1]).to_course()
        self.assertEqual(old.state, "inactivo")
        self.assertEqual(current.state, "activo")
        self.assertEqual(old.group_id, 90000011)

    def test_json_keys(self) -> None:
        payload = HistoryCourse.from_api(HISTORY_ROWS[0]).to_dict()
        self.assertEqual(payload["group_id"], 90000011)
        self.assertEqual(payload["enrollment"], "MATRICULA REGULAR")


class ResolveAnyTests(IsolatedHomeMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.make_home()
        self.client = FakeHistoryClient()

    def test_current_catalog_wins(self) -> None:
        course = resolve_any(self.client, courses(), "1")  # type: ignore[arg-type]
        self.assertEqual(course.name, "CURSO DE EJEMPLO UNO")
        self.assertEqual(self.client.history_calls, 0)

    def test_falls_back_to_the_historial_by_group_id(self) -> None:
        course = resolve_any(self.client, courses(), "90000011")  # type: ignore[arg-type]
        self.assertEqual(course.name, "CURSO HISTORICO UNO")
        self.assertEqual(course.period, "209802")

    def test_falls_back_by_name(self) -> None:
        course = resolve_any(self.client, courses(), "historico uno")  # type: ignore[arg-type]
        self.assertEqual(course.group_id, 90000011)

    def test_unknown_token_still_raises(self) -> None:
        with self.assertRaises(UsageError):
            resolve_any(self.client, courses(), "no existe")  # type: ignore[arg-type]


class HistorialCommandTests(IsolatedHomeMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        patcher = mock.patch("autonoma_cli.commands.client_for", return_value=FakeHistoryClient())
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(argv))
        return code, output.getvalue()

    def test_lists_periods_and_states(self) -> None:
        code, out = self.run_main("historial")
        self.assertEqual(code, 0)
        self.assertIn("2 cursos · periodos 209901, 209802", out)
        self.assertIn("APROBADA", out)
        self.assertIn("EN PROCESO", out)
        self.assertIn("90000011", out)

    def test_period_filter(self) -> None:
        code, out = self.run_main("historial", "--periodo", "209802")
        self.assertEqual(code, 0)
        self.assertIn("1 curso · periodo 209802", out)
        self.assertNotIn("HISTORICO DOS", out)

    def test_json(self) -> None:
        code, out = self.run_main("historial", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual([row["group_id"] for row in payload], [90000012, 90000011])

    def test_course_text_filter(self) -> None:
        code, out = self.run_main("historial", "--curso", "historico uno")
        self.assertEqual(code, 0)
        self.assertIn("90000011", out)
        self.assertNotIn("90000012", out)

    def test_empty_filter_says_so(self) -> None:
        code, out = self.run_main("historial", "--ciclo", "1")
        self.assertEqual(code, 0)
        self.assertIn("Sin cursos que coincidan con el filtro.", out)


if __name__ == "__main__":
    unittest.main()
