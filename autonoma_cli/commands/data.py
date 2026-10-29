"""Datos del campus con cache: cursos, horario y recursos de un curso."""

from __future__ import annotations

from typing import Sequence

from .. import cache
from ..client import CampusClient
from ..models import ClassSession, Course, Resource


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
