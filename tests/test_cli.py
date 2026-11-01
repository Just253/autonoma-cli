from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

from autonoma_cli import ui
from autonoma_cli.cli import (
    build_parser,
    main,
)
from autonoma_cli.commands import run_horario
from autonoma_cli.selectors import (
    filter_courses,
    kind_filter,
    parse_day,
    parse_sessions,
    resolve_course,
    schedule_range,
)
from autonoma_cli.errors import (
    AuthenticationError,
    AutonomaError,
    CampusError,
    UsageError,
)
from autonoma_cli.models import ClassSession, Course

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
        )
        for argv in documented:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertTrue(callable(args.func))

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
            ["cursos", "--ciclo", "8", "--periodo", "209901", "--carrera", "software", "--activos"]
        )
        self.assertEqual((args.ciclo, args.periodo, args.carrera, args.activos),
                         ("8", "209901", "software", True))
        horario = parser.parse_args(["horario", "--ciclo", "2"])
        self.assertEqual(horario.ciclo, "2")
        self.assertFalse(horario.activos)


def mixed_courses() -> list[Course]:
    """Tres cursos: dos periodos, dos carreras, uno inactivo."""

    return [
        Course.from_api(
            {
                "nGruCodigo": 90000001,
                "asignatura": "CURSO DE EJEMPLO UNO",
                "periodo": "209901",
                "ciclo": "8",
                "carrera": "INGENIERÍA DE EJEMPLO",
                "EstadoCurso": "1",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000002,
                "asignatura": "CURSO DE EJEMPLO DOS",
                "periodo": "209802",
                "ciclo": "2",
                "carrera": "INGENIERÍA DE EJEMPLO",
                "EstadoCurso": "2",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000003,
                "asignatura": "CURSO DE EJEMPLO TRES",
                "periodo": "209901",
                "ciclo": "2",
                "carrera": "ADMINISTRACIÓN DE EJEMPLO",
                "EstadoCurso": "1",
            },
            BASE,
        ),
    ]


class CourseFilterTests(unittest.TestCase):
    def test_without_filters_returns_everything(self) -> None:
        self.assertEqual(len(filter_courses(mixed_courses())), 3)

    def test_by_cycle_and_period(self) -> None:
        self.assertEqual(
            [course.name for course in filter_courses(mixed_courses(), cycle="2")],
            ["CURSO DE EJEMPLO DOS", "CURSO DE EJEMPLO TRES"],
        )
        self.assertEqual(
            [course.name for course in filter_courses(mixed_courses(), period="209901")],
            ["CURSO DE EJEMPLO UNO", "CURSO DE EJEMPLO TRES"],
        )

    def test_by_career_ignores_accents_and_case(self) -> None:
        found = filter_courses(mixed_courses(), career="administracion")
        self.assertEqual([course.name for course in found], ["CURSO DE EJEMPLO TRES"])

    def test_active_only(self) -> None:
        found = filter_courses(mixed_courses(), active=True)
        self.assertEqual(
            [course.name for course in found], ["CURSO DE EJEMPLO UNO", "CURSO DE EJEMPLO TRES"]
        )

    def test_filters_combine(self) -> None:
        self.assertEqual(
            filter_courses(mixed_courses(), period="209901", cycle="2", active=True),
            [mixed_courses()[2]],
        )

    def test_unknown_combination_is_empty(self) -> None:
        self.assertEqual(filter_courses(mixed_courses(), period="209999"), [])


def schedule_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "curso": None,
        "hoy": False,
        "manana": False,
        "dia": None,
        "todo": False,
        "desde": None,
        "hasta": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ScheduleDayTests(unittest.TestCase):
    def test_dd_mm_yyyy(self) -> None:
        self.assertEqual(parse_day("15/03/2099"), date(2099, 3, 15))

    def test_iso(self) -> None:
        self.assertEqual(parse_day("2099-03-15"), date(2099, 3, 15))

    def test_hoy_y_manana(self) -> None:
        today = date.today()
        self.assertEqual(parse_day("hoy"), today)
        self.assertEqual(parse_day("manana"), today + timedelta(days=1))

    def test_invalid_raises(self) -> None:
        with self.assertRaises(UsageError):
            parse_day("32/13/2026")


class ScheduleRangeTests(unittest.TestCase):
    def test_default_is_one_week(self) -> None:
        start, end = schedule_range(schedule_args())
        self.assertEqual(start, date.today())
        self.assertEqual(end, date.today() + timedelta(days=6))

    def test_hoy(self) -> None:
        self.assertEqual(schedule_range(schedule_args(hoy=True)), (date.today(), date.today()))

    def test_dia(self) -> None:
        self.assertEqual(
            schedule_range(schedule_args(dia="01/11/2026")),
            (date(2026, 11, 1), date(2026, 11, 1)),
        )

    def test_desde_hasta(self) -> None:
        self.assertEqual(
            schedule_range(schedule_args(desde="01/11/2026", hasta="05/11/2026")),
            (date(2026, 11, 1), date(2026, 11, 5)),
        )

    def test_todo(self) -> None:
        self.assertEqual(schedule_range(schedule_args(todo=True)), (None, None))

    def test_reversed_raises(self) -> None:
        with self.assertRaises(UsageError):
            schedule_range(schedule_args(desde="05/11/2026", hasta="01/11/2026"))


# --------------------------------------------------------------------------- #
# run_horario de punta a punta (sin red)
# --------------------------------------------------------------------------- #

# Registros crudos tal como los devuelve getProgramacionAlumnoGrupo.
SCHEDULE_RECORDS: dict[str, list[dict[str, object]]] = {
    "90000001": [
        {
            "nSesion": 1,
            "cSesion": "01",
            "tema": "Introduccion a la materia",
            "fecha": "03/11/2026 08:00 a 10:00",
            "tipo": "Presencial",
            "ambiente": "B-202 (Aula)",
        },
        {
            "nSesion": 2,
            "cSesion": "02",
            "tema": "Practica de laboratorio",
            "fecha": "05/11/2026 14:00 a 16:00",
            "tipo": "Presencial",
            "ambiente": "A-101 (Laboratorio)",
        },
        {
            "nSesion": 3,
            "cSesion": "03",
            "tema": "Clase posterior al rango",
            "fecha": "10/11/2026 09:00 a 11:00",
            "tipo": "Presencial",
            "ambiente": "B-202 (Aula)",
        },
    ],
    "90000002": [
        {
            "nSesion": 1,
            "cSesion": "01",
            "tema": "Seminario de repaso",
            "fecha": "05/11/2026 08:00 a 10:00",
            "tipo": "Sincrona",
            "ambiente": "C-303 (Aula)",
        },
        {
            "nSesion": 2,
            "cSesion": "02",
            "tema": "Clase anterior al rango",
            "fecha": "01/11/2026 07:00 a 09:00",
            "tipo": "Sincrona",
            "ambiente": "C-303 (Aula)",
        },
    ],
}


class FakeCampusClient:
    """Cliente de mentira: mismas firmas que usa run_horario, sin red."""

    base_url = BASE
    student_code = "2024000001"

    def __init__(self) -> None:
        self.schedule_calls: list[tuple[object, str]] = []

    def get_courses(self) -> list[Course]:
        return courses()

    def get_schedule(self, group_id: int | str, *, course: str = "") -> list[ClassSession]:
        self.schedule_calls.append((group_id, course))
        records = SCHEDULE_RECORDS.get(str(group_id), [])
        return [
            ClassSession.from_api(record, group_id=group_id, course=course)
            for record in records
        ]


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


class IsolatedHomeMixin:
    """AUTONOMA_CLI_HOME a una carpeta temporal: ni lee ni escribe la cache real."""

    tmp: tempfile.TemporaryDirectory[str]

    def make_home(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(
            os.environ,
            {"AUTONOMA_CLI_HOME": self.tmp.name},
            clear=False,
        )
        env.start()
        self.addCleanup(env.stop)


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


# --------------------------------------------------------------------------- #
# Codigos de salida de main()
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Los ejemplos de la documentacion, ejecutados de punta a punta
# --------------------------------------------------------------------------- #


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
