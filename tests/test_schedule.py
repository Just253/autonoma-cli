from __future__ import annotations

import argparse
import unittest
from datetime import date, timedelta

from autonoma_cli.errors import UsageError
from autonoma_cli.selectors import parse_day, schedule_range


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


if __name__ == "__main__":
    unittest.main()
