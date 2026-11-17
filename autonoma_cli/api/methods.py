"""WebMethods del campus: ruta, payload y mapeo a los modelos.

Cada funcion recibe el contexto de ``call`` y devuelve datos ya parseados; los
endpoints se llaman entre si aca adentro para no repetir una peticion.
"""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Mapping, Sequence

from ..errors import ProtocolError
from ..models import (
    AcademicSummary,
    ClassSession,
    Course,
    CourseGrades,
    Resource,
    SessionTopic,
)
from .call import ApiContext, call
from .json import records

PERFIL_ALUMNO = 13
TABLERO_PAGE = "/Campus/ua/Tablero/Perfil/Camp_Virt_Perfil.aspx"
CURRICULA_PAGE = "/Modulos/Campus/MisCursos/Ca_Mc_CursosMatriculados.aspx"
HISTORY_PAGE = "/CampusVirtual/ua/Alumno/MisCursos/Alu_HistorialCursos.aspx"
# cTablas exacto del tablero (docs/API.md seccion 8): cada nombre vuelve como clave.
TABLERO_TABLES = (
    "Malla_Curricular,Malla_Curricular_grafPromedioNotaByCiclo,"
    "Malla_Curricular_grafAvanceCarrera,Malla_Curricular_grafTipoCurso,"
    "DatosPersonales,Competencias,PuestoAcademico"
)


def get_courses(ctx: ApiContext) -> list[Course]:
    data = call(ctx, "Alu_ObtenerCursosActuales", {})
    if not isinstance(data, list):
        raise ProtocolError("La lista de cursos no tiene el formato esperado.")
    return [
        Course.from_api(item, ctx.base_url)
        for item in data
        if isinstance(item, Mapping) and item.get("nGruCodigo")
    ]


def get_course_detail(ctx: ApiContext, group_id: int | str, session: int = 0) -> Any:
    return call(
        ctx,
        "getInformationDetailCurso",
        {"nGruCodigo": group_id, "nSesion": int(session), "nPerfil": PERFIL_ALUMNO},
    )


def get_curricula(ctx: ApiContext, kind: int = 1) -> list[Mapping[str, Any]]:
    """Curriculas del alumno (1 = carrera, 2 = extraacademicos)."""

    data = call(
        ctx,
        "obtenerUniOrgCurriculo",
        {"cPerCodigo": ctx.auth.ensure_student_code(), "nTipCur": kind},
        page=CURRICULA_PAGE,
    )
    return records(data)


def get_history(ctx: ApiContext) -> list[Mapping[str, Any]]:
    """Cursos de todos los periodos: recorre cada curricula del alumno."""

    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for curriculum in get_curricula(ctx):
        data = call(
            ctx,
            "ObtenerCursosByCurricula",
            {
                "nCurCodigo": curriculum.get("nCurCodigo"),
                "cPerCodigo": "",
                "cTablas": "HISTORIAL_CURSOS,PERIODO_HISTORIAL_CURSOS",
            },
            page=HISTORY_PAGE,
        )
        if not isinstance(data, Mapping):
            continue
        for row in records(data.get("HISTORIAL_CURSOS")):
            key = str(row.get("nGruCodigo"))
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return rows


def get_grades(ctx: ApiContext, group_id: int | str) -> CourseGrades:
    """Criterios del periodo abierto (``getNotasAlumnoGrupo``)."""

    data = call(ctx, "getNotasAlumnoGrupo", {"nGruCodigo": group_id})
    if not isinstance(data, Mapping):
        raise ProtocolError("Las notas del curso no tienen el formato esperado.")
    return CourseGrades.from_api(data, group_id=group_id)


def get_academic_summary(ctx: ApiContext) -> AcademicSummary:
    """Promedio oficial del tablero (``ObtenerDataAvanceCarrera``)."""

    student = ctx.auth.ensure_student_code()
    current = call(
        ctx, "ObtenerCurrriculasActuales", {"cPerCodigo": student}, page=TABLERO_PAGE
    )
    rows = records(current)
    if not rows and isinstance(current, Mapping):
        # Sin clave conocida: la primera lista de filas es la de curriculas.
        rows = [
            item
            for value in current.values()
            if isinstance(value, list)
            for item in value
            if isinstance(item, Mapping)
        ]
    enrollment = rows[0].get("nPerAluRegCodigo") if rows else None
    if not enrollment:
        raise ProtocolError("El tablero no devolvio la matricula del alumno.")
    data = call(
        ctx,
        "ObtenerDataAvanceCarrera",
        {"cPerCodigo": "", "nPerAluRegCodigo": enrollment, "cTablas": TABLERO_TABLES},
        page=TABLERO_PAGE,
    )
    if not isinstance(data, Mapping):
        raise ProtocolError("El avance de carrera no tiene el formato esperado.")
    return AcademicSummary.from_api(data)


def get_syllabus(ctx: ApiContext, group_id: int | str) -> list[SessionTopic]:
    data = get_course_detail(ctx, group_id, 0)
    topics: Iterable[Any] = ()
    if isinstance(data, Mapping):
        raw = data.get("silabo")
        if isinstance(raw, list):
            topics = raw
    return [SessionTopic.from_api(item) for item in topics if isinstance(item, Mapping)]


def get_schedule(
    ctx: ApiContext, group_id: int | str, *, course: str = ""
) -> list[ClassSession]:
    """Programacion del grupo: fechas, horarios y aula de cada sesion."""

    data = call(ctx, "getProgramacionAlumnoGrupo", {"nGruCodigo": group_id})
    return [
        ClassSession.from_api(item, group_id=group_id, course=course)
        for item in records(data)
    ]


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
