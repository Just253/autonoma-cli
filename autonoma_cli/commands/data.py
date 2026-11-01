"""Datos del campus con cache: cursos, horario y recursos de un curso."""

from __future__ import annotations

from typing import Sequence

from .. import cache, selectors
from ..client import CampusClient
from ..errors import UsageError
from ..models import ClassSession, Course, HistoryCourse, Resource


def catalog(client: CampusClient, *, refresh: bool = False) -> list[Course]:
    """Cursos del periodo con cache de 6 horas (el campus responde lento)."""
    items = cache.ensure(
        cache.for_campus(client.base_url),
        f"cursos:{client.student_code}",
        ttl=cache.MAX_AGE_CURSOS,
        fetch=lambda: [dict(course.raw or {}) for course in client.get_courses()],
        force=refresh,
    )
    records = items if isinstance(items, list) else []
    return [Course.from_api(item, client.base_url) for item in records if isinstance(item, dict)]


def schedule(
    client: CampusClient, courses: Sequence[Course], *, refresh: bool = False
) -> list[ClassSession]:
    """Programacion de todos los cursos, con cache de 6 horas por grupo."""
    store = cache.for_campus(client.base_url)
    entries: list[ClassSession] = []
    for course in courses:
        records = cache.ensure(
            store,
            f"horario:{course.group_id}",
            ttl=cache.MAX_AGE_HORARIO,
            fetch=lambda course=course: [
                dict(entry.raw or {})
                for entry in client.get_schedule(course.group_id, course=course.name)
            ],
            force=refresh,
        )
        entries.extend(
            ClassSession.from_api(item, group_id=course.group_id, course=course.name)
            for item in (records if isinstance(records, list) else ()) if isinstance(item, dict)
        )
    return entries


def _resources_of(
    client: CampusClient, course: Course, sessions: Sequence[int] | None
) -> list[tuple[int, list[Resource]]]:
    if sessions:
        return [(session, client.get_session_resources(course.group_id, session)) for session in sessions]
    return client.iter_session_resources(course.group_id)


def history(client: CampusClient, *, refresh: bool = False) -> list[HistoryCourse]:
    """Cursos de todos los periodos, con cache de 6 horas."""

    items = cache.ensure(
        cache.for_campus(client.base_url),
        f"historial:{client.student_code or 'anon'}",
        ttl=cache.MAX_AGE_CURSOS,
        fetch=lambda: [dict(row) for row in client.get_history()],
        force=refresh,
    )
    records = items if isinstance(items, list) else []
    return [HistoryCourse.from_api(item) for item in records if isinstance(item, dict)]


def resolve_any(
    client: CampusClient, courses: Sequence[Course], token: str, *, refresh: bool = False
) -> Course:
    """Resuelve en el catalogo actual y, si no esta, en el historial."""

    try:
        return selectors.resolve_course(courses, token)
    except UsageError as current_error:
        text = (token or "").strip()
        found = [
            course
            for course in history(client, refresh=refresh)
            if str(course.group_id) == text or course.matches(text)
        ]
        if len(found) == 1:
            return found[0].to_course()
        if len(found) > 1:
            listing = "\n".join(f"  - {course.name} ({course.period})" for course in found)
            raise UsageError(
                f"Varios cursos del historial coinciden con {text!r}:\n{listing}"
            ) from None
        raise current_error
