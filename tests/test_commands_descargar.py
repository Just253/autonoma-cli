"""`autonoma descargar`: las listas de recursos se cachean una hora."""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from autonoma_cli import cache, config, ui
from autonoma_cli.cli import main
from autonoma_cli.errors import SessionExpiredError
from autonoma_cli.models import Course, Resource
from support.home import IsolatedHomeMixin

BASE = "https://virtual.autonoma.edu.pe"
STUDENT = "2024000001"
GROUP = 90000001
RESOURCES_KEY = f"recursos:{STUDENT}:{GROUP}"


def _resource(session: int, title: str) -> Resource:
    return Resource.from_api(
        {
            "cTitulo": title,
            "nDocLinTipo": 2,
            "nDocLinNum": session,
            "nSesion": session,
            "cSesion": f"{session:02d}",
            "url": f"s{session}.pdf",
        },
        BASE,
        session=session,
    )


class FakeDownloadClient:
    """Cliente de mentira: cuenta las listas pedidas y no toca la red."""

    base_url = BASE
    student_code = STUDENT

    def __init__(self) -> None:
        self.list_calls = 0
        self.session_calls: list[int] = []

    def get_courses(self) -> list[Course]:
        return [
            Course.from_api(
                {"nGruCodigo": GROUP, "asignatura": "CURSO DE EJEMPLO"}, BASE
            )
        ]

    def iter_session_resources(self, group_id: object) -> list[tuple[int, list[Resource]]]:
        self.list_calls += 1
        return [
            (1, [_resource(1, "MATERIAL UNO")]),
            (2, [_resource(2, "MATERIAL DOS")]),
        ]

    def get_session_resources(self, group_id: object, session: int) -> list[Resource]:
        self.session_calls.append(session)
        return [_resource(session, f"MATERIAL {session}")]


class ExpiredClient(FakeDownloadClient):
    """Listas normales y descargas con la sesion vencida."""

    headers = {"User-Agent": "autonoma-cli/0 (+uso-personal)"}
    referer = ""

    def __init__(self) -> None:
        super().__init__()
        self.sends = 0

    def send(self, request: object, *, cookies: bool = True) -> object:
        self.sends += 1
        raise SessionExpiredError("La sesion del campus expiro.")


class _CacheCase(IsolatedHomeMixin):
    """Base con cliente falso y HOME temporal; sin tests propios."""

    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        self.client = FakeDownloadClient()
        patcher = mock.patch(
            "autonoma_cli.commands.client_for", return_value=self.client
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = Path(self.tmp.name) / "descargas"

    def run_main(self, *argv: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()):
            return main(["--out", str(self.out), *argv])


class DescargarCacheTests(_CacheCase, unittest.TestCase):
    """La segunda corrida no pide listas; --refresh y --sesion si piden."""

    def test_second_run_uses_the_cached_lists(self) -> None:
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.assertEqual(self.client.list_calls, 1)

    def test_refresh_reads_the_lists_again(self) -> None:
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco", "--refresh"), 0)
        self.assertEqual(self.client.list_calls, 2)

    def test_broken_cached_value_is_ignored(self) -> None:
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        path = config.cache_dir() / cache.CACHE_FILE
        document = json.loads(path.read_text(encoding="utf-8"))
        document["entries"][RESOURCES_KEY] = {"at": 1e12, "value": "basura"}
        path.write_text(json.dumps(document), encoding="utf-8")

        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)

        self.assertEqual(self.client.list_calls, 2, "un valor roto se vuelve a pedir")
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(document["entries"][RESOURCES_KEY]["value"], list)

    def test_sesion_does_not_use_the_cache(self) -> None:
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco", "--sesion", "2"), 0)
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco", "--sesion", "2"), 0)
        self.assertEqual(self.client.session_calls, [2, 2])
        self.assertEqual(self.client.list_calls, 0)


class ExpiredSessionTests(IsolatedHomeMixin, unittest.TestCase):
    """Con la cookie vencida, la corrida en serie se corta en el primer archivo."""

    def setUp(self) -> None:
        self.make_home()
        ui.configure_color(False)
        self.client = ExpiredClient()
        patcher = mock.patch(
            "autonoma_cli.commands.client_for", return_value=self.client
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = Path(self.tmp.name) / "descargas"

    def test_la_corrida_en_serie_corta_en_el_primer_vencimiento(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = main([
                "--out", str(self.out), "descargar", str(GROUP), "--json", "--workers", "1",
            ])

        self.assertEqual(code, 1)
        self.assertEqual(
            self.client.sends, 2, "un reintento con cookie y se corta el resto del plan"
        )


class RecursosCacheTests(_CacheCase, unittest.TestCase):
    """`recursos` usa la misma cache y respeta --refresh."""

    def test_recursos_refresh_reads_the_lists_again(self) -> None:
        self.assertEqual(self.run_main("recursos", str(GROUP)), 0)
        self.assertEqual(self.run_main("recursos", str(GROUP), "--refresh"), 0)
        self.assertEqual(self.client.list_calls, 2)


class IdentityTests(_CacheCase, unittest.TestCase):
    """Sin codigo de alumno no se cachea; dos alumnos no comparten entradas."""

    def test_sin_codigo_no_cachea(self) -> None:
        self.client.student_code = ""
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.assertEqual(self.client.list_calls, 2)

    def test_dos_alumnos_no_comparten_la_lista(self) -> None:
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.client.student_code = "2024000002"
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.assertEqual(self.client.list_calls, 2)

    def test_un_par_a_medio_escribir_se_vuelve_a_pedir(self) -> None:
        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        path = config.cache_dir() / cache.CACHE_FILE
        document = json.loads(path.read_text(encoding="utf-8"))
        document["entries"][RESOURCES_KEY] = {
            "at": 1e12,
            "value": [[1, [{"cTitulo": "OK"}, "basura"]]],
        }
        path.write_text(json.dumps(document), encoding="utf-8")

        self.assertEqual(self.run_main("descargar", str(GROUP), "--seco"), 0)
        self.assertEqual(self.client.list_calls, 2, "el par roto invalida el documento")


if __name__ == "__main__":
    unittest.main()
