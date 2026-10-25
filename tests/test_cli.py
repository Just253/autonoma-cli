from __future__ import annotations

import unittest

from autonoma_cli.cli import build_parser, kind_filter, parse_sessions, resolve_course
from autonoma_cli.errors import UsageError
from autonoma_cli.models import Course

BASE = "https://virtual.autonoma.edu.pe"


def courses() -> list[Course]:
    return [
        Course.from_api({"nGruCodigo": 90000001, "asignatura": "CURSO DE EJEMPLO UNO", "codigo": "PISOP00001"}, BASE),
        Course.from_api({"nGruCodigo": 90000002, "asignatura": "CURSO DE EJEMPLO DOS", "codigo": "PISOP00002"}, BASE),
    ]


class ResolveCourseTests(unittest.TestCase):
    def test_by_index(self) -> None:
        self.assertEqual(resolve_course(courses(), "2").group_id, 90000002)

    def test_by_group_id(self) -> None:
        self.assertEqual(resolve_course(courses(), "90000001").name, "CURSO DE EJEMPLO UNO")

    def test_by_name(self) -> None:
        self.assertEqual(resolve_course(courses(), "ejemplo uno").group_id, 90000001)

    def test_unknown_raises(self) -> None:
        with self.assertRaises(UsageError):
            resolve_course(courses(), "matematica")

    def test_ambiguous_raises(self) -> None:
        with self.assertRaises(UsageError):
            resolve_course(courses(), "PISOP")

    def test_empty_raises(self) -> None:
        with self.assertRaises(UsageError):
            resolve_course(courses(), "")


class FilterTests(unittest.TestCase):
    def test_kind_filters(self) -> None:
        self.assertEqual(kind_filter("archivo"), {2})
        self.assertEqual(kind_filter("tarea"), {4})
        self.assertIsNone(kind_filter("todo"))

    def test_unknown_kind(self) -> None:
        with self.assertRaises(UsageError):
            kind_filter("exe")

    def test_parse_sessions_deduplicates(self) -> None:
        self.assertEqual(parse_sessions([1, 1, 3]), [1, 3])

    def test_parse_sessions_none(self) -> None:
        self.assertIsNone(parse_sessions(None))


class ParserTests(unittest.TestCase):
    def test_known_commands(self) -> None:
        parser = build_parser()
        for command in ("login", "logout", "whoami", "credenciales", "cursos", "curso", "recursos", "descargar", "todo", "cache"):
            with self.subTest(command=command):
                args = parser.parse_args([command] + (["1"] if command in {"curso", "recursos", "descargar"} else []))
                self.assertTrue(callable(args.func))

    def test_download_defaults(self) -> None:
        args = build_parser().parse_args(["descargar", "1"])
        self.assertEqual(args.tipo, "archivo")
        self.assertFalse(args.seco)
        self.assertFalse(args.forzar)


if __name__ == "__main__":
    unittest.main()
