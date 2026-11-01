"""Comandos `cursos` y `curso`."""

from __future__ import annotations

import argparse

from .. import render, selectors, ui
from ..client import CampusClient
from ..models import Resource
from .data import catalog


def run_cursos(client: CampusClient, args: argparse.Namespace) -> int:
    courses = selectors.filter_courses(
        catalog(client, refresh=args.refresh),
        cycle=args.ciclo,
        period=args.periodo,
        career=args.carrera,
        active=args.activos,
    )
    if args.json:
        render.emit_json([course.to_dict() for course in courses])
        return 0
    if not courses:
        render.text("Sin cursos que coincidan con el filtro.")
        return 0

    periods = sorted({course.period for course in courses if course.period})
    plural = "periodo" if len(periods) == 1 else "periodos"
    counted = f"{len(courses)} curso{'s' if len(courses) != 1 else ''}"
    render.text(ui.bold(f"{counted} · {plural} {', '.join(periods) or '-'}"))
    rows = [
        [
            index,
            course.name[:34],
            course.code,
            course.group,
            course.cycle,
            course.period,
            course.state,
            course.teacher[:18],
            course.resources_count,
        ]
        for index, course in enumerate(courses, start=1)
    ]
    render.text()
    render.text(ui.table(
        ["#", "Curso", "Codigo", "Grupo", "Ciclo", "Periodo", "Estado", "Docente", "Rec."],
        rows,
        max_widths=[3, 34, 12, 8, 5, 7, 9, 18, 4],
        aligns=["right", "left", "left", "left", "right", "left", "left", "left", "right"],
    ))
    render.text()
    filtered = args.ciclo or args.periodo or args.carrera or args.activos
    if filtered:
        render.text(ui.dim(
            "Con filtros el indice es relativo: usa el nGruCodigo "
            f"(autonoma recursos {courses[0].group_id})."
        ))
    else:
        render.text(ui.dim(f"Usa el indice o el nGruCodigo: autonoma recursos {courses[0].group_id}"))
    return 0


def run_curso(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    course = selectors.resolve_course(courses, args.curso)
    topics = client.get_syllabus(course.group_id)
    detail = client.get_course_detail(course.group_id, 0)
    active_resources: list[Resource] = []
    if isinstance(detail, dict):
        raw_records = detail.get("recursos")
        if isinstance(raw_records, list):
            active_resources = [
                Resource.from_api(item, client.base_url)
                for item in raw_records
                if isinstance(item, dict)
            ]

    if args.json:
        render.emit_json(
            {
                "course": course.to_dict(),
                "sessions": [topic.to_dict() for topic in topics],
                "active_session_resources": [item.to_dict() for item in active_resources],
            }
        )
        return 0

    render.print_course_header(course)
    if course.syllabus_url:
        render.text(f"  Silabo: {course.syllabus_url}")
    if topics:
        render.print_syllabus(topics)
    if active_resources:
        render.text(ui.dim(f"\nSesion activa ({active_resources[0].session_label}) · {len(active_resources)} recursos"))
    render.text()
    render.text(
        ui.dim(
            f"Siguiente paso: autonoma horario {course.group_id} "
            f"| autonoma recursos {course.group_id} "
            f"| autonoma descargar {course.group_id}"
        )
    )
    return 0
