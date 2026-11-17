"""`autonoma notas --refresh`: la bandera llega hasta el historial."""

from __future__ import annotations

import contextlib
import io
import unittest

from autonoma_cli.commands import run_notas
from support.grades import FakeGradesApi, notas_args
from support.home import IsolatedHomeMixin


class NotasRefreshTests(IsolatedHomeMixin, unittest.TestCase):
    """El historial tambien se refresca cuando el usuario pasa --refresh."""

    def setUp(self) -> None:
        self.make_home()
        self.client = FakeGradesApi()

    def run_notas(self, **overrides: object) -> int:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            return run_notas(self.client, notas_args(**overrides))

    def test_refresh_refetches_the_historico(self) -> None:
        self.assertEqual(self.run_notas(curso="90000011", json=True), 0)
        self.assertEqual(self.run_notas(curso="90000011", json=True), 0)
        self.assertEqual(self.client.history_calls, 1, "la cache sirve la segunda vez")

        self.assertEqual(self.run_notas(curso="90000011", json=True, refresh=True), 0)
        self.assertEqual(
            self.client.history_calls,
            3,
            "con --refresh se pide de nuevo: una vez para resolver el curso y otra "
            "para el detalle",
        )


if __name__ == "__main__":
    unittest.main()
