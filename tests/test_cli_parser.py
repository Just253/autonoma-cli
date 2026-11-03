from __future__ import annotations

import unittest

from autonoma_cli.cli import build_parser


class ParserTests(unittest.TestCase):
    def test_known_commands(self) -> None:
        parser = build_parser()
        for command in (
            "login",
            "logout",
            "whoami",
            "credenciales",
            "cursos",
            "curso",
            "horario",
            "recursos",
            "descargar",
            "todo",
            "cache",
            "notas",
        ):
            with self.subTest(command=command):
                args = parser.parse_args([command] + (["1"] if command in {"curso", "recursos", "descargar"} else []))
                self.assertTrue(callable(args.func))

    def test_horario_alias(self) -> None:
        args = build_parser().parse_args(["aula", "--hoy"])
        self.assertTrue(callable(args.func))
        self.assertTrue(args.hoy)

    def test_download_defaults(self) -> None:
        args = build_parser().parse_args(["descargar", "1"])
        self.assertEqual(args.tipo, "archivo")
        self.assertFalse(args.seco)
        self.assertFalse(args.forzar)

    def test_documented_invocations_parse(self) -> None:
        """Los ejemplos del README y de la skill tienen que parsear tal cual."""

        parser = build_parser()
        documented = (
            ["cursos", "--json"],
            ["curso", "1", "--json"],
            ["horario", "--todo", "--json"],
            ["recursos", "1", "--json"],
            ["descargar", "1", "--out", "salida"],
            ["todo", "--out", "salida"],
            ["cursos", "--no-color"],
            ["descargar", "1", "--seco", "--solo", "presentacion"],
            ["notas", "--json"],
            ["notas", "1", "--json"],
            ["notas", "--todos", "--promedio"],
        )
        for argv in documented:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(callable(args.func))

    def test_notas_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["notas", "2", "--todos", "--promedio", "--periodo", "209901", "--ciclo", "8"]
        )
        self.assertEqual(args.curso, "2")
        self.assertTrue(args.todos)
        self.assertTrue(args.promedio)
        self.assertEqual((args.periodo, args.ciclo), ("209901", "8"))
        self.assertFalse(args.activos)
        self.assertFalse(args.json)
        self.assertFalse(parser.parse_args(["notas"]).todos)
        self.assertIsNone(parser.parse_args(["notas"]).curso)

    def test_global_options_work_before_and_after_the_command(self) -> None:
        parser = build_parser()
        self.assertTrue(parser.parse_args(["cursos", "--json"]).json)
        self.assertTrue(parser.parse_args(["--json", "cursos"]).json)
        self.assertFalse(parser.parse_args(["cursos"]).json)
        self.assertTrue(parser.parse_args(["cursos", "--no-color"]).no_color)
        self.assertTrue(parser.parse_args(["--no-color", "cursos"]).no_color)
        self.assertEqual(parser.parse_args(["descargar", "1", "--out", "salida"]).out, "salida")
        self.assertEqual(parser.parse_args(["--out", "salida", "descargar", "1"]).out, "salida")
        self.assertIsNone(parser.parse_args(["descargar", "1"]).out)

    def test_course_filters_parse(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["cursos", "--ciclo", "8", "--periodo", "209901", "--carrera", "ejemplo", "--activos"]
        )
        self.assertEqual((args.ciclo, args.periodo, args.carrera, args.activos),
                         ("8", "209901", "ejemplo", True))
        horario = parser.parse_args(["horario", "--ciclo", "2"])
        self.assertEqual(horario.ciclo, "2")
        self.assertFalse(horario.activos)


if __name__ == "__main__":
    unittest.main()
