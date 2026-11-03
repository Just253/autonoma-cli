from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from autonoma_cli import ui
from autonoma_cli.cli import main
from autonoma_cli.models import Course
from support import FakeCampusClient, IsolatedHomeMixin, mixed_courses


class MixedCoursesClient(FakeCampusClient):
    def get_courses(self) -> list[Course]:
        return mixed_courses()


class CursosCommandTests(IsolatedHomeMixin, unittest.TestCase):
    """La tabla de `cursos` tiene que separar periodo, estado y carrera."""

    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        patcher = mock.patch("autonoma_cli.commands.client_for", return_value=MixedCoursesClient())
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(argv))
        return code, output.getvalue()

    def test_header_names_every_period(self) -> None:
        code, out = self.run_main("cursos")
        self.assertEqual(code, 0)
        self.assertIn("3 cursos · periodos 209802, 209901", out)
        self.assertIn("Periodo", out)
        self.assertIn("Estado", out)
        self.assertIn("inactivo", out)

    def test_period_filter_reaches_json(self) -> None:
        code, out = self.run_main("cursos", "--periodo", "209802", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual([course["name"] for course in payload], ["CURSO DE EJEMPLO DOS"])
        self.assertEqual(payload[0]["career"], "INGENIERÍA DE EJEMPLO")

    def test_empty_filter_says_so(self) -> None:
        code, out = self.run_main("cursos", "--ciclo", "9")
        self.assertEqual(code, 0)
        self.assertIn("Sin cursos que coincidan con el filtro.", out)

    def test_single_course_header_is_singular(self) -> None:
        code, out = self.run_main("cursos", "--periodo", "209802")
        self.assertEqual(code, 0)
        self.assertIn("1 curso · periodo 209802", out)


if __name__ == "__main__":
    unittest.main()
