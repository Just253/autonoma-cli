"""Comando `notas`: criterios, historico y promedio oficial."""

from __future__ import annotations

import argparse

from .. import render, selectors, ui
from ..client import CampusClient
from ..models import AcademicSummary, Course, CourseGrades, HistoryCourse
from .data import catalog, history, resolve_any


def _summary(course: Course, grades: CourseGrades) -> dict[str, object]:
    return {"group_id": course.group_id, "course": course.name, "period": course.period,
            "cycle": course.cycle, "average": grades.average,
            "average_value": grades.average_value, "percent": grades.percent,
            "updated": grades.updated}


def _closed(row: HistoryCourse) -> dict[str, object]:
    return {"group_id": row.group_id, "course": row.name, "period": row.period,
            "cycle": row.cycle, "grade": row.grade,
            "grade_value": row.grade_value, "closed": True}


def _emit(payload: dict[str, object], official: AcademicSummary | None) -> None:
    render.emit_json(payload if official is None
                     else {"course": payload, "official": official.to_dict()})


def _closed_courses(client: CampusClient, args: argparse.Namespace,
                    active_ids: set[str]) -> list[HistoryCourse]:
    rows = selectors.filter_courses(history(client, refresh=args.refresh),
                                    cycle=args.ciclo, period=args.periodo, career=args.carrera)
    return sorted((row for row in rows if str(row.group_id) not in active_ids),
                  key=lambda row: (row.period, row.name), reverse=True)


def _detail(client: CampusClient, args: argparse.Namespace, course: Course,
            current_ids: set[str], official: AcademicSummary | None) -> int:
    row = None
    if str(course.group_id) not in current_ids:
        row = next((item for item in history(client, refresh=False)
                    if str(item.group_id) == str(course.group_id)), None)
    if row is not None:
        payload = _closed(row)
        if args.json:
            _emit(payload, official)
            return 0
        render.print_closed_course(course, row.grade)
    else:
        grades = client.get_grades(course.group_id)
        payload = _summary(course, grades)
        payload["items"] = [item.to_dict() for item in grades.items]
        if args.json:
            _emit(payload, official)
            return 0
        render.print_grades_detail(course, grades)
    if official is not None:
        render.print_academic_summary(official)
    return 0


def run_notas(client: CampusClient, args: argparse.Namespace) -> int:
    all_courses = catalog(client, refresh=args.refresh)
    current_ids = {str(course.group_id) for course in all_courses}
    courses = selectors.filter_courses(all_courses, cycle=args.ciclo, period=args.periodo,
                                       career=args.carrera, active=args.activos)
    if args.curso:
        course = resolve_any(client, courses, args.curso, refresh=args.refresh)
        official = client.get_academic_summary() if args.promedio else None
        return _detail(client, args, course, current_ids, official)
    official = client.get_academic_summary() if args.promedio else None
    courses = [course for course in courses if course.state == "activo"]
    pairs = [(course, client.get_grades(course.group_id)) for course in courses]
    payload = [_summary(course, grades) for course, grades in pairs]
    closed = _closed_courses(client, args, current_ids) if args.todos else []
    if args.todos or official is not None:
        body: dict[str, object] = {"courses": payload}
        if args.todos:
            body["closed"] = [_closed(row) for row in closed]
        if official is not None:
            body["official"] = official.to_dict()
    else:
        body = payload
    if args.json:
        render.emit_json(body)
        return 0
    if pairs:
        render.print_grades_summary(pairs)
    else:
        render.text("Sin cursos que coincidan con el filtro.")
    if args.todos:
        render.text()
        render.text(ui.bold("Periodos cerrados"))
        if closed:
            render.print_closed_grades(closed)
        else:
            render.text(ui.dim("Sin cursos cerrados fuera del periodo activo."))
    if official is not None:
        render.print_academic_summary(official)
    return 0
