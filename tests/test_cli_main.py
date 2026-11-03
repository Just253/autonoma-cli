from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from autonoma_cli import ui
from autonoma_cli.cli import main
from autonoma_cli.errors import (
    AuthenticationError,
    AutonomaError,
    CampusError,
    UsageError,
)
from support import FakeCampusClient, IsolatedHomeMixin


class MainExitCodeTests(IsolatedHomeMixin, unittest.TestCase):
    def setUp(self) -> None:
        self.make_home()

    def run_main(self, error: BaseException) -> tuple[int, str, str]:
        """whoami toca client_for como primera instruccion: ahi inyectamos el error."""

        out, err = io.StringIO(), io.StringIO()
        with mock.patch("autonoma_cli.commands.client_for", side_effect=error), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["whoami"])
        return code, out.getvalue(), err.getvalue()

    def test_usage_error_returns_2(self) -> None:
        code, _, err = self.run_main(UsageError("curso desconocido"))
        self.assertEqual(code, 2)
        self.assertTrue(err.startswith("error: "))

    def test_authentication_error_returns_3(self) -> None:
        code, _, err = self.run_main(AuthenticationError("clave incorrecta"))
        self.assertEqual(code, 3)
        self.assertTrue(err.startswith("login: "))
        self.assertIn("autonoma login", err)

    def test_campus_error_returns_4(self) -> None:
        code, _, err = self.run_main(CampusError("el campus no responde"))
        self.assertEqual(code, 4)
        self.assertTrue(err.startswith("campus: "))

    def test_other_autonoma_error_returns_1(self) -> None:
        code, _, err = self.run_main(AutonomaError("algo salio mal"))
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error: "))

    def test_keyboard_interrupt_returns_130(self) -> None:
        code, _, err = self.run_main(KeyboardInterrupt())
        self.assertEqual(code, 130)
        self.assertIn("Cancelado.", err)


class DocumentedInvocationsRunTests(IsolatedHomeMixin, unittest.TestCase):
    """`autonoma cursos --json` no solo parsea: tiene que devolver JSON."""

    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        patcher = mock.patch("autonoma_cli.commands.client_for", return_value=FakeCampusClient())
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *argv: str) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(list(argv))
        return code, output.getvalue()

    def test_cursos_json_after_the_command(self) -> None:
        code, out = self.run_main("cursos", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["name"], "CURSO DE EJEMPLO UNO")

    def test_horario_json_after_the_command(self) -> None:
        code, out = self.run_main("horario", "--todo", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["count"], len(payload["sessions"]))


if __name__ == "__main__":
    unittest.main()
