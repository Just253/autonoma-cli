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


class DescargarCacheTests(IsolatedHomeMixin, unittest.TestCase):
    """La segunda corrida no pide listas; --refresh y --sesion si piden."""

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


if __name__ == "__main__":
    unittest.main()
