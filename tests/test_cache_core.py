from __future__ import annotations

import io
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from autonoma_cli.cache import Cache
from autonoma_cli.cli import main
from support.cache import (
    BASE,
    COURSES_KEY,
    NOW,
    CacheTestCase,
    FakeClient,
    cache_path,
    document,
    entry,
    raw_course,
)


class CacheTests(CacheTestCase):
    def test_get_is_none_for_missing_key(self) -> None:
        store = Cache(cache_path(), BASE)
        store.load()
        self.assertIsNone(store.get("no-existe", 60, now=NOW))

    def test_clear_removes_document_and_entries(self) -> None:
        store = Cache(cache_path(), BASE)
        store.load()
        store.set("cursos:1", [], now=NOW)
        store.save()
        self.assertTrue(cache_path().exists())

        store.clear()

        self.assertEqual(store.entries, {})
        self.assertFalse(cache_path().exists())

    def test_save_failure_is_silent(self) -> None:
        store = Cache(cache_path(), BASE)
        store.load()
        store.set("cursos:1", [], now=NOW)

        with patch("autonoma_cli.cache.config.write_private_text", side_effect=OSError("disco lleno")):
            store.save()

        self.assertEqual(store.get("cursos:1", 60, now=NOW), [])


class RefreshCoursesBugTests(CacheTestCase):
    """Con cache de cursos fresca, --refresh tiene que volver a pedirlos."""

    def setUp(self) -> None:
        super().setUp()
        self.client = FakeClient()
        patcher = mock.patch("autonoma_cli.commands.client_for", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.out = Path(self._tmp.name) / "descargas"
        self.write(document({COURSES_KEY: entry(time.time(), [raw_course(1, "CURSO CACHEADO")])}))

    def run_main(self, *argv: str) -> int:
        with redirect_stdout(io.StringIO()):
            return main(list(argv))

    def test_horario_with_refresh_refetches_courses(self) -> None:
        self.assertEqual(self.run_main("horario", "--refresh"), 0)
        self.assertEqual(self.client.course_calls, 1)

    def test_horario_without_refresh_uses_the_cache(self) -> None:
        self.assertEqual(self.run_main("horario"), 0)
        self.assertEqual(self.client.course_calls, 0)

    def test_global_refresh_before_the_command_still_works(self) -> None:
        self.assertEqual(self.run_main("--refresh", "horario"), 0)
        self.assertEqual(self.client.course_calls, 1)

    def test_curso_with_refresh_refetches_courses(self) -> None:
        self.assertEqual(self.run_main("curso", "1", "--refresh"), 0)
        self.assertEqual(self.client.course_calls, 1)

    def test_descargar_with_refresh_refetches_courses(self) -> None:
        code = self.run_main(
            "--out", str(self.out), "descargar", "1", "--refresh", "--seco"
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.client.course_calls, 1)

    def test_recursos_with_refresh_refetches_courses(self) -> None:
        self.assertEqual(self.run_main("recursos", "1", "--refresh"), 0)
        self.assertEqual(self.client.course_calls, 1)


if __name__ == "__main__":
    unittest.main()
