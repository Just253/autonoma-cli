from __future__ import annotations

import unittest
from unittest.mock import patch

from autonoma_cli import cache, config
from autonoma_cli.commands import catalog
from support.cache import (
    BASE,
    COURSES_KEY,
    NOW,
    OTHER,
    CacheTestCase,
    FakeClient,
    cache_path,
    document,
    entry,
    raw_course,
)


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


if __name__ == "__main__":
    unittest.main()
