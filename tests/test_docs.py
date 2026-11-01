"""Los ejemplos de la documentación tienen que parsear de verdad.

Si un flag cambia y la doc no, este test falla antes que un usuario.
"""

from __future__ import annotations

import re
import shlex
import unittest
from pathlib import Path

from autonoma_cli.cli import build_parser

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").glob("*.md"))]
FENCE = re.compile(r"^```[A-Za-z]*\s*$")
COMMENT = re.compile(r"\s+#")


def examples() -> list[tuple[Path, int, str]]:
    """Líneas ``autonoma …`` dentro de bloques de código, sin comentarios."""

    found: list[tuple[Path, int, str]] = []
    for path in MARKDOWN:
        inside = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line):
                inside = not inside
                continue
            if not inside:
                continue
            text = COMMENT.split(line, maxsplit=1)[0].strip()
            if text.startswith("autonoma "):
                found.append((path, number, text))
    return found


class DocumentedExamplesTests(unittest.TestCase):
    def test_there_are_examples(self) -> None:
        self.assertGreater(len(examples()), 10)

    def test_every_example_parses(self) -> None:
        parser = build_parser()
        for path, number, command in examples():
            if "--help" in command or "--version" in command:
                continue
            with self.subTest(file=path.name, line=number, command=command):
                try:
                    parser.parse_args(shlex.split(command)[1:])
                except SystemExit as exc:  # argparse sale con 2 si algo no existe
                    self.fail(f"{path.name}:{number} no parsea: {command} ({exc})")

    def test_every_command_is_documented(self) -> None:
        parser = build_parser()
        subparsers = parser._subparsers._group_actions[0]  # type: ignore[union-attr]
        seen: set[int] = set()
        canonical: list[str] = []
        for name, subparser in subparsers.choices.items():
            if id(subparser) not in seen:  # los alias comparten el mismo parser
                seen.add(id(subparser))
                canonical.append(name)

        reference = (ROOT / "docs" / "CLI.md").read_text(encoding="utf-8")
        missing = [
            f"autonoma {name}"
            for name in canonical
            if not re.search(rf"autonoma {re.escape(name)}(?![a-z])", reference)
        ]
        self.assertFalse(missing, f"docs/CLI.md no documenta: {missing}")


if __name__ == "__main__":
    unittest.main()
