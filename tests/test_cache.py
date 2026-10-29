from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from autonoma_cli import cache, config
from autonoma_cli.cache import Cache
from autonoma_cli.cli import catalog, main, schedule
from autonoma_cli.models import ClassSession, Course

BASE = "https://virtual.autonoma.edu.pe"
OTHER = "https://otro.example.edu.pe"
NOW = 1_800_000_000.0
STUDENT = "20240001"
COURSES_KEY = f"cursos:{STUDENT}"


def raw_course(group_id: int, name: str) -> dict:
    return {"nGruCodigo": group_id, "asignatura": name, "codigo": f"COD{group_id}"}


def raw_schedule(topic: str) -> dict:
    return {
        "fecha": "20/10/2026 08:00 a 10:00",
        "asignatura": "CURSO DE EJEMPLO",
        "nSesion": 1,
        "cSesion": "01",
        "tema": topic,
    }


def entry(at: float, value: object) -> dict:
    return {"at": at, "value": value}


def document(entries: dict, *, base_url: str = BASE) -> dict:
    return {"version": cache.VERSION, "base_url": base_url, "entries": entries}


def cache_path() -> Path:
    return config.cache_dir() / cache.CACHE_FILE


class FakeClient:
    """Cliente de mentira: cuenta llamadas y no toca la red."""

    def __init__(self, *, base_url: str = BASE) -> None:
        self.base_url = base_url
        self.student_code = STUDENT
        self.course_calls = 0
        self.schedule_calls: list[object] = []

    def get_courses(self) -> list[Course]:
        self.course_calls += 1
        return [Course.from_api(raw_course(90000001, "CURSO FRESCO"), self.base_url)]

    def get_schedule(self, group_id: object, *, course: str = "") -> list[ClassSession]:
        self.schedule_calls.append(group_id)
        data = raw_schedule("Tema fresco")
        data["nGruCodigo"] = group_id
        data["asignatura"] = course or data["asignatura"]
        return [ClassSession.from_api(data, group_id=group_id, course=course)]

    def get_syllabus(self, group_id: object) -> list:
        return []

    def get_course_detail(self, group_id: object, session: int) -> dict:
        return {}

    def iter_session_resources(self, group_id: object) -> list:
        return []


class CacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.dict(os.environ, {"AUTONOMA_CLI_HOME": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, payload: dict) -> Path:
        path = cache_path()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @staticmethod
    def read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def course(self, group_id: int, name: str) -> Course:
        return Course.from_api(raw_course(group_id, name), BASE)


class CoursesCacheTests(CacheTestCase):
    def test_missing_file_fetches_and_writes(self) -> None:
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            courses = catalog(client)

        path = cache_path()
        self.assertTrue(path.exists())
        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])
        document_ = self.read(path)
        self.assertEqual(document_["version"], 1)
        self.assertEqual(document_["base_url"], BASE)
        record = document_["entries"][COURSES_KEY]
        self.assertEqual(record["at"], NOW)
        self.assertEqual([item["nGruCodigo"] for item in record["value"]], [90000001])

    def test_corrupt_json_refetches_and_rewrites(self) -> None:
        path = cache_path()
        path.write_text("{esto no es json", encoding="utf-8")
        client = FakeClient()

        courses = catalog(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])
        self.assertEqual(self.read(path)["entries"][COURSES_KEY]["value"][0]["nGruCodigo"], 90000001)

    def test_other_base_url_refetches(self) -> None:
        self.write(document({COURSES_KEY: entry(NOW, [raw_course(1, "CURSO CACHEADO")])}, base_url=OTHER))
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            courses = catalog(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])
        self.assertEqual(self.read(cache_path())["base_url"], BASE)

    def test_other_document_version_refetches(self) -> None:
        document_ = document({COURSES_KEY: entry(NOW, [raw_course(1, "CURSO CACHEADO")])})
        document_["version"] = 99
        self.write(document_)
        client = FakeClient()

        courses = catalog(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])

    def test_expired_ttl_refetches(self) -> None:
        self.write(
            document(
                {
                    COURSES_KEY: entry(
                        NOW - cache.MAX_AGE_CURSOS - 1, [raw_course(1, "CURSO CACHEADO")]
                    )
                }
            )
        )
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            courses = catalog(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])

    def test_ttl_boundary_refetches(self) -> None:
        # La comparacion es estricta (< ttl): justo en el limite ya se considera vencida.
        self.write(
            document(
                {COURSES_KEY: entry(NOW - cache.MAX_AGE_CURSOS, [raw_course(1, "CURSO CACHEADO")])}
            )
        )
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            catalog(client)

        self.assertEqual(client.course_calls, 1)

    def test_fresh_cache_skips_client(self) -> None:
        path = self.write(
            document(
                {
                    COURSES_KEY: entry(
                        NOW - cache.MAX_AGE_CURSOS + 1, [raw_course(1, "CURSO CACHEADO")]
                    )
                }
            )
        )
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            courses = catalog(client)

        self.assertEqual(client.course_calls, 0)
        self.assertEqual([course.name for course in courses], ["CURSO CACHEADO"])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_refresh_refetches_fresh_cache(self) -> None:
        self.write(document({COURSES_KEY: entry(NOW, [raw_course(1, "CURSO CACHEADO")])}))
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            courses = catalog(client, refresh=True)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])

    def test_empty_list_is_a_valid_cached_value(self) -> None:
        # Cambio deliberado: una lista vacia ya no fuerza refetch.
        path = self.write(document({COURSES_KEY: entry(NOW, [])}))
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            courses = catalog(client)

        self.assertEqual(client.course_calls, 0)
        self.assertEqual(courses, [])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_items_without_dicts_return_empty_without_fetching(self) -> None:
        # Lista no vacia pero sin dicts: se toma como cache valida y devuelve [].
        path = self.write(document({COURSES_KEY: entry(NOW, ["basura", 42])}))
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            courses = catalog(client)

        self.assertEqual(client.course_calls, 0)
        self.assertEqual(courses, [])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_entry_without_valid_timestamp_refetches(self) -> None:
        self.write(document({COURSES_KEY: {"at": "ayer", "value": [raw_course(1, "CURSO CACHEADO")]}}))
        client = FakeClient()

        courses = catalog(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])

    def test_legacy_documents_are_removed_on_save(self) -> None:
        legacy = [config.cache_dir() / name for name in cache.LEGACY_FILES]
        for path in legacy:
            path.write_text("{}", encoding="utf-8")
        client = FakeClient()

        catalog(client)

        self.assertTrue(all(not path.exists() for path in legacy))
        self.assertTrue(cache_path().exists())


class ScheduleCacheTests(CacheTestCase):
    def test_missing_file_fetches_every_group_and_writes(self) -> None:
        client = FakeClient()
        courses = [self.course(111, "CURSO UNO"), self.course(222, "CURSO DOS")]

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            entries = schedule(client, courses)

        self.assertEqual(client.schedule_calls, [111, 222])
        self.assertEqual(len(entries), 2)
        document_ = self.read(cache_path())
        self.assertEqual(document_["base_url"], BASE)
        self.assertEqual(sorted(document_["entries"]), ["horario:111", "horario:222"])
        self.assertEqual(document_["entries"]["horario:111"]["at"], NOW)
        self.assertEqual(document_["entries"]["horario:111"]["value"][0]["nGruCodigo"], 111)

    def test_partial_reuse_only_fetches_stale_group(self) -> None:
        self.write(
            document(
                {
                    "horario:111": entry(NOW - 10, [raw_schedule("Tema cacheado")]),
                    "horario:222": entry(
                        NOW - cache.MAX_AGE_HORARIO - 1, [raw_schedule("Tema viejo")]
                    ),
                }
            )
        )
        client = FakeClient()
        courses = [self.course(111, "CURSO UNO"), self.course(222, "CURSO DOS")]

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            entries = schedule(client, courses)

        self.assertEqual(client.schedule_calls, [222])
        self.assertEqual([entry_.title for entry_ in entries], ["Tema cacheado", "Tema fresco"])
        document_ = self.read(cache_path())
        self.assertEqual(document_["entries"]["horario:111"]["at"], NOW - 10)
        self.assertEqual(document_["entries"]["horario:222"]["at"], NOW)

    def test_all_fresh_does_not_rewrite_file(self) -> None:
        path = self.write(document({"horario:111": entry(NOW - 10, [raw_schedule("Tema cacheado")])}))
        document_ = self.read(path)
        document_["marca"] = "no reescribir"
        path.write_text(json.dumps(document_), encoding="utf-8")
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            entries = schedule(client, [self.course(111, "CURSO UNO")])

        self.assertEqual(client.schedule_calls, [])
        self.assertEqual([entry_.title for entry_ in entries], ["Tema cacheado"])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_other_base_url_refetches(self) -> None:
        self.write(
            document(
                {"horario:111": entry(NOW, [raw_schedule("Tema de otro campus")])},
                base_url=OTHER,
            )
        )
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            entries = schedule(client, [self.course(111, "CURSO UNO")])

        self.assertEqual(client.schedule_calls, [111])
        self.assertEqual([entry_.title for entry_ in entries], ["Tema fresco"])

    def test_refresh_ignores_fresh_cache(self) -> None:
        self.write(document({"horario:111": entry(NOW, [raw_schedule("Tema cacheado")])}))
        client = FakeClient()

        with patch("autonoma_cli.cache.time.time", return_value=NOW):
            entries = schedule(client, [self.course(111, "CURSO UNO")], refresh=True)

        self.assertEqual(client.schedule_calls, [111])
        self.assertEqual([entry_.title for entry_ in entries], ["Tema fresco"])


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
        patcher = mock.patch("autonoma_cli.cli.client_for", return_value=self.client)
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
