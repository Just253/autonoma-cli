"""Salida `--json` de `autonoma notas`: resumen, detalle, cerrados y promedio."""

from __future__ import annotations

import contextlib
import io
import json
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


if __name__ == "__main__":
    unittest.main()
