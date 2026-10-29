from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autonoma_cli.cli import (
    COURSE_CACHE_TTL,
    SCHEDULE_CACHE_TTL,
    courses_cache_path,
    load_courses,
    load_schedule,
    schedule_cache_path,
)
from autonoma_cli.models import ClassSession, Course

BASE = "https://virtual.autonoma.edu.pe"
OTHER = "https://otro.example.edu.pe"
NOW = 1_800_000_000.0


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


def courses_document(fetched_at: float, *, base_url: str = BASE, items: list) -> dict:
    return {"fetched_at": fetched_at, "base_url": base_url, "items": items}


def schedule_document(items: dict, *, base_url: str = BASE) -> dict:
    return {"fetched_at": NOW, "base_url": base_url, "items": items}


def record(fetched_at: float, records: list) -> dict:
    return {"fetched_at": fetched_at, "course": "CURSO DE EJEMPLO", "records": records}


class FakeClient:
    """Cliente de mentira: cuenta llamadas y no toca la red."""

    def __init__(self, *, base_url: str = BASE) -> None:
        self.base_url = base_url
        self.student_code = "20240001"
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


class CacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.dict(os.environ, {"AUTONOMA_CLI_HOME": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_courses(self, document: dict) -> Path:
        path = courses_cache_path()
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def write_schedule(self, document: dict) -> Path:
        path = schedule_cache_path()
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    @staticmethod
    def read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def course(self, group_id: int, name: str) -> Course:
        return Course.from_api(raw_course(group_id, name), BASE)


class CoursesCacheTests(CacheTestCase):
    def test_missing_file_fetches_and_writes(self) -> None:
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            courses = load_courses(client)

        path = courses_cache_path()
        self.assertTrue(path.exists())
        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])
        document = self.read(path)
        self.assertEqual(document["base_url"], BASE)
        self.assertEqual(document["student_code"], "20240001")
        self.assertEqual(document["fetched_at"], NOW)
        self.assertEqual([item["nGruCodigo"] for item in document["items"]], [90000001])

    def test_corrupt_json_refetches_and_rewrites(self) -> None:
        path = courses_cache_path()
        path.write_text("{esto no es json", encoding="utf-8")
        client = FakeClient()

        courses = load_courses(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])
        self.assertEqual(self.read(path)["items"][0]["nGruCodigo"], 90000001)

    def test_other_base_url_refetches(self) -> None:
        self.write_courses(
            courses_document(NOW, base_url=OTHER, items=[raw_course(1, "CURSO CACHEADO")])
        )
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            courses = load_courses(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])
        self.assertEqual(self.read(courses_cache_path())["base_url"], BASE)

    def test_expired_ttl_refetches(self) -> None:
        self.write_courses(
            courses_document(
                NOW - COURSE_CACHE_TTL - 1,
                items=[raw_course(1, "CURSO CACHEADO")],
            )
        )
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            courses = load_courses(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])

    def test_ttl_boundary_refetches(self) -> None:
        # La comparacion es estricta (< TTL): justo en el limite ya se considera vencida.
        self.write_courses(
            courses_document(
                NOW - COURSE_CACHE_TTL,
                items=[raw_course(1, "CURSO CACHEADO")],
            )
        )
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            load_courses(client)

        self.assertEqual(client.course_calls, 1)

    def test_fresh_cache_skips_client(self) -> None:
        path = self.write_courses(
            courses_document(
                NOW - COURSE_CACHE_TTL + 1,
                items=[raw_course(1, "CURSO CACHEADO")],
            )
        )
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            courses = load_courses(client)

        self.assertEqual(client.course_calls, 0)
        self.assertEqual([course.name for course in courses], ["CURSO CACHEADO"])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_refresh_refetches_fresh_cache(self) -> None:
        self.write_courses(
            courses_document(NOW, items=[raw_course(1, "CURSO CACHEADO")])
        )
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            courses = load_courses(client, refresh=True)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])

    def test_empty_items_is_not_a_valid_cache(self) -> None:
        path = self.write_courses(courses_document(NOW, items=[]))
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            courses = load_courses(client)

        self.assertEqual(client.course_calls, 1)
        self.assertEqual([course.name for course in courses], ["CURSO FRESCO"])
        self.assertNotEqual(path.read_text(encoding="utf-8"), before)
        self.assertEqual(len(self.read(path)["items"]), 1)

    def test_items_without_dicts_return_empty_without_fetching(self) -> None:
        # Lista no vacia pero sin dicts: se toma como cache valida y devuelve [].
        path = self.write_courses(courses_document(NOW, items=["basura", 42]))
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            courses = load_courses(client)

        self.assertEqual(client.course_calls, 0)
        self.assertEqual(courses, [])
        self.assertEqual(path.read_text(encoding="utf-8"), before)


class ScheduleCacheTests(CacheTestCase):
    def test_missing_file_fetches_every_group_and_writes(self) -> None:
        client = FakeClient()
        courses = [self.course(111, "CURSO UNO"), self.course(222, "CURSO DOS")]

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            entries = load_schedule(client, courses)

        self.assertEqual(client.schedule_calls, [111, 222])
        self.assertEqual(len(entries), 2)
        document = self.read(schedule_cache_path())
        self.assertEqual(document["base_url"], BASE)
        self.assertEqual(sorted(document["items"]), ["111", "222"])
        self.assertEqual(document["items"]["111"]["fetched_at"], NOW)

    def test_partial_reuse_only_fetches_stale_group(self) -> None:
        self.write_schedule(
            schedule_document(
                {
                    "111": record(NOW - 10, [raw_schedule("Tema cacheado")]),
                    "222": record(
                        NOW - SCHEDULE_CACHE_TTL - 1, [raw_schedule("Tema viejo")]
                    ),
                }
            )
        )
        client = FakeClient()
        courses = [self.course(111, "CURSO UNO"), self.course(222, "CURSO DOS")]

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            entries = load_schedule(client, courses)

        self.assertEqual(client.schedule_calls, [222])
        self.assertEqual([entry.title for entry in entries], ["Tema cacheado", "Tema fresco"])
        document = self.read(schedule_cache_path())
        self.assertEqual(document["items"]["111"]["fetched_at"], NOW - 10)
        self.assertEqual(document["items"]["222"]["fetched_at"], NOW)

    def test_all_fresh_does_not_rewrite_file(self) -> None:
        path = self.write_schedule(
            schedule_document(
                {"111": record(NOW - 10, [raw_schedule("Tema cacheado")])}
            )
        )
        document = self.read(path)
        document["marca"] = "no reescribir"
        path.write_text(json.dumps(document), encoding="utf-8")
        before = path.read_text(encoding="utf-8")
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            entries = load_schedule(client, [self.course(111, "CURSO UNO")])

        self.assertEqual(client.schedule_calls, [])
        self.assertEqual([entry.title for entry in entries], ["Tema cacheado"])
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_other_base_url_refetches(self) -> None:
        self.write_schedule(
            schedule_document(
                {"111": record(NOW, [raw_schedule("Tema de otro campus")])},
                base_url=OTHER,
            )
        )
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            entries = load_schedule(client, [self.course(111, "CURSO UNO")])

        self.assertEqual(client.schedule_calls, [111])
        self.assertEqual([entry.title for entry in entries], ["Tema fresco"])

    def test_refresh_ignores_fresh_cache(self) -> None:
        self.write_schedule(
            schedule_document(
                {"111": record(NOW, [raw_schedule("Tema cacheado")])}
            )
        )
        client = FakeClient()

        with patch("autonoma_cli.cli.time.time", return_value=NOW):
            entries = load_schedule(
                client, [self.course(111, "CURSO UNO")], refresh=True
            )

        self.assertEqual(client.schedule_calls, [111])
        self.assertEqual([entry.title for entry in entries], ["Tema fresco"])


if __name__ == "__main__":
    unittest.main()
