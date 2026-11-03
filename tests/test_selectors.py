from __future__ import annotations

import unittest

from autonoma_cli.errors import UsageError
from autonoma_cli.selectors import (
    filter_courses,
    kind_filter,
    parse_sessions,
    resolve_course,
)
from support import courses, mixed_courses


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


if __name__ == "__main__":
    unittest.main()
