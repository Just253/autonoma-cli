from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from autonoma_cli import cache
from autonoma_cli.commands import schedule
from support.cache import (
    BASE,
    NOW,
    OTHER,
    CacheTestCase,
    FakeClient,
    cache_path,
    document,
    entry,
    raw_schedule,
)


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


if __name__ == "__main__":
    unittest.main()
