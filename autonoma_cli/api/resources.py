"""Recursos de las sesiones de un curso: lectura por sesion y recorrido.

Cada funcion pide ``getInformationDetailCurso`` y mapea la respuesta; el
recorrido usa el silabo para saber que sesiones existen.
"""

from __future__ import annotations

from typing import Iterator, Sequence

from ..models import Resource
from .call import ApiContext
from .json import records
from .methods import get_course_detail, get_syllabus


def get_session_resources(
    ctx: ApiContext, group_id: int | str, session: int
) -> list[Resource]:
    data = get_course_detail(ctx, group_id, session)
    return [
        Resource.from_api(item, ctx.base_url, session=session)
        for item in records(data)
    ]


def active_session_resources(ctx: ApiContext, group_id: int | str) -> list[Resource]:
    """Recursos de la sesion activa, con la lectura que ya trae el curso.

    ``getInformationDetailCurso`` con ``nSesion=0`` devuelve el silabo y los
    recursos de la semana en curso en una sola peticion. Las carpetas traen
    su ``nSesion`` (docs/GUIA.md), asi que alcanza para no recorrer el resto.
    """

    return get_session_resources(ctx, group_id, 0)


def iter_session_resources(
    ctx: ApiContext,
    group_id: int | str,
    sessions: Sequence[int] | None = None,
    *,
    stop_after_empty: int = 2,
    max_sessions: int,
) -> list[tuple[int, list[Resource]]]:
    """Recorre las sesiones y devuelve (numero, recursos) de cada una.

    Si no se indican sesiones, se usan las del silabo; si el silabo no
    viene, se prueban 1..max_sessions y se corta tras N sesiones vacias.
    """

    return list(
        iter_session_resources_lazy(
            ctx,
            group_id,
            sessions,
            stop_after_empty=stop_after_empty,
            max_sessions=max_sessions,
        )
    )


def iter_session_resources_lazy(
    ctx: ApiContext,
    group_id: int | str,
    sessions: Sequence[int] | None = None,
    *,
    stop_after_empty: int = 2,
    max_sessions: int,
) -> Iterator[tuple[int, list[Resource]]]:
    """Como ``iter_session_resources`` pero pide una sesion por vez.

    El consumidor puede cortar en la primera coincidencia: las sesiones que
    faltan no se piden. Es la version que usa ``entregar`` para buscar una
    carpeta sin recorrer el curso entero.
    """

    if sessions:
        numbers = list(sessions)
        limit = 0
    else:
        numbers = [
            topic.number for topic in get_syllabus(ctx, group_id) if topic.number
        ]
        if numbers:
            limit = 0
        else:
            numbers = list(range(1, max_sessions + 1))
            limit = stop_after_empty

    empty_run = 0
    for number in numbers:
        resources = [
            item
            for item in get_session_resources(ctx, group_id, number)
            if item.kind != 0
        ]
        yield number, resources
        if resources:
            empty_run = 0
        else:
            empty_run += 1
            if limit and empty_run >= limit:
                break
