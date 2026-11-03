from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest

from autonoma_cli import ui
from autonoma_cli.commands import run_horario
from support import FakeCampusClient, IsolatedHomeMixin


def horario_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "curso": None,
        "hoy": False,
        "manana": False,
        "dia": None,
        "todo": False,
        "desde": None,
        "hasta": None,
        "refresh": False,
        "json": False,
        "ciclo": None,
        "periodo": None,
        "carrera": None,
        "activos": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class HorarioCommandTests(IsolatedHomeMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        self.client = FakeCampusClient()

    def run_horario(self, **overrides: object) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = run_horario(self.client, horario_args(**overrides))
        return code, output.getvalue()

    def test_range_prints_only_sessions_inside_it(self) -> None:
        code, out = self.run_horario(desde="03/11/2026", hasta="07/11/2026")
        self.assertEqual(code, 0)
        self.assertIn("Del 03/11/2026 al 07/11/2026", out)
        self.assertIn("03/11/2026", out)
        self.assertIn("05/11/2026", out)
        self.assertIn("CURSO DE EJEMPLO UNO", out)
        self.assertIn("CURSO DE EJEMPLO DOS", out)
        self.assertNotIn("10/11/2026", out)
        self.assertNotIn("01/11/2026", out)

    def test_sessions_are_sorted_by_date_then_time(self) -> None:
        code, out = self.run_horario(desde="03/11/2026", hasta="07/11/2026", json=True)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["from"], "2026-11-03")
        self.assertEqual(payload["to"], "2026-11-07")
        self.assertEqual(payload["count"], 3)
        self.assertEqual(
            [(item["date"], item["start_time"]) for item in payload["sessions"]],
            [
                ("2026-11-03", "08:00"),
                ("2026-11-05", "08:00"),
                ("2026-11-05", "14:00"),
            ],
        )

    def test_single_day(self) -> None:
        code, out = self.run_horario(dia="05/11/2026")
        self.assertEqual(code, 0)
        # La etiqueta del dia puede ser "Hoy" si el test corre ese mismo dia.
        self.assertIn("05/11/2026 · 2 sesiones", out)
        self.assertIn("Seminario de repaso", out)
        self.assertIn("Practica de laboratorio", out)
        self.assertNotIn("03/11/2026", out)
        self.assertNotIn("10/11/2026", out)

    def test_empty_range_exits_zero(self) -> None:
        code, out = self.run_horario(desde="20/12/2026", hasta="21/12/2026")
        self.assertEqual(code, 0)
        self.assertIn("Sin clases en ese rango.", out)

    def test_asks_schedule_once_per_course(self) -> None:
        self.run_horario(todo=True)
        self.assertEqual(
            self.client.schedule_calls,
            [
                (90000001, "CURSO DE EJEMPLO UNO"),
                (90000002, "CURSO DE EJEMPLO DOS"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
