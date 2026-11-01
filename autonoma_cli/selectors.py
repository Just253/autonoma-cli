"""Selectores de entrada: cursos, fechas, sesiones y tipos de recurso."""

from __future__ import annotations

import argparse
import datetime as dt
from typing import Protocol, Sequence

from .errors import UsageError
from .models import Course, fold, parse_date

KIND_FILTERS: dict[str, set[int] | None] = {
    "archivo": {2},
    "tarea": {4},
    "evaluacion": {5},
    "foro": {7},
    "scorm": {10},
    "todo": None,
}


def parse_day(text: str) -> dt.date:
    """Acepta una fecha (dd/mm/aaaa) o ``hoy`` / ``manana`` / ``ayer``."""

    cleaned = (text or "").strip().lower()
    today = dt.date.today()
    if cleaned in {"hoy", "today"}:
        return today
    if cleaned in {"manana", "mañana", "tomorrow"}:
        return today + dt.timedelta(days=1)
    if cleaned in {"ayer", "yesterday"}:
        return today - dt.timedelta(days=1)
    day = parse_date(cleaned)
    if day is None:
        raise UsageError(f"Fecha no valida: {text!r}. Usa dd/mm/aaaa (o hoy, manana, ayer).")
    return day


def schedule_range(args: argparse.Namespace) -> tuple[dt.date | None, dt.date | None]:
    """Rango pedido en la linea de comandos; ``(None, None)`` = todo el periodo."""

    today = dt.date.today()
    if args.todo:
        return None, None
    if args.hoy:
        return today, today
    if args.manana:
        tomorrow = today + dt.timedelta(days=1)
        return tomorrow, tomorrow
    if args.dia:
        day = parse_day(args.dia)
        return day, day

    start = parse_day(args.desde) if args.desde else today
    end = parse_day(args.hasta) if args.hasta else start + dt.timedelta(days=6)
    if end < start:
        raise UsageError("--hasta no puede ser anterior a --desde.")
    return start, end


class CourseFields(Protocol):
    """Lo que necesitan los filtros: sirve Course y HistoryCourse."""

    cycle: str
    period: str
    career: str
    state: str


def filter_courses(
    courses: Sequence[CourseFields],
    *,
    cycle: str | None = None,
    period: str | None = None,
    career: str | None = None,
    active: bool = False,
) -> list[Course]:
    """Cursos que pasan los filtros de ciclo, periodo, carrera y estado.

    Los textos se comparan sin acentos ni mayusculas; ciclo y periodo, por
    igualdad. Sin filtros devuelve la lista tal cual.
    """

    result = list(courses)
    if cycle:
        wanted = fold(cycle)
        result = [course for course in result if fold(course.cycle) == wanted]
    if period:
        wanted = fold(period)
        result = [course for course in result if fold(course.period) == wanted]
    if career:
        wanted = fold(career)
        result = [course for course in result if wanted in fold(course.career)]
    if active:
        result = [course for course in result if course.state == "activo"]
    return result


def resolve_course(courses: Sequence[Course], token: str) -> Course:
    """Acepta indice (1..N), nGruCodigo o texto libre."""

    token = (token or "").strip()
    if not token:
        raise UsageError("Indica un curso: indice, nGruCodigo o parte del nombre.")
    if token.isdigit():
        number = int(token)
        for course in courses:
            if str(course.group_id) == token:
                return course
        if 1 <= number <= len(courses):
            return courses[number - 1]
    matches = [course for course in courses if course.matches(token)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise UsageError(f"No hay ningun curso que coincida con {token!r}.")
    listing = "\n".join(f"  - {course.name} ({course.group_id})" for course in matches)
    raise UsageError(f"Varios cursos coinciden con {token!r}:\n{listing}")


def kind_filter(name: str) -> set[int] | None:
    try:
        return KIND_FILTERS[name]
    except KeyError as exc:
        raise UsageError(f"Tipo desconocido: {name}") from exc


def parse_sessions(values: Sequence[int] | None, maximum: int | None = None) -> list[int] | None:
    if not values:
        return None
    sessions: list[int] = []
    for value in values:
        if maximum is not None and not 1 <= value <= maximum:
            raise UsageError(f"La sesion {value} no existe en este curso (1..{maximum}).")
        if value not in sessions:
            sessions.append(value)
    return sessions
