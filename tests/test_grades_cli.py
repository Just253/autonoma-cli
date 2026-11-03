"""`autonoma notas` de punta a punta con el parser real."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from autonoma_cli import ui
from autonoma_cli.cli import main
from support.grades import FakeGradesApi
from support.home import IsolatedHomeMixin


class NotasMainTests(IsolatedHomeMixin, unittest.TestCase):
    """`autonoma notas --json` de punta a punta con el parser real."""

    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        patcher = mock.patch(
            "autonoma_cli.commands.client_for", return_value=FakeGradesApi()
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
