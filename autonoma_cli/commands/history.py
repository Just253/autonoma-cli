"""Comando `historial`: cursos de todos los periodos del alumno."""

from __future__ import annotations

import argparse

from .. import render, selectors, ui
from ..client import CampusClient
from .data import history


def run_historial(client: CampusClient, args: argparse.Namespace) -> int:
    courses = selectors.filter_courses(
        history(client, refresh=args.refresh),
        cycle=args.ciclo,
        period=args.periodo,
        career=args.carrera,
    )
    if args.curso:
        courses = [course for course in courses if course.matches(args.curso)]
    courses = sorted(courses, key=lambda course: (course.period, course.name), reverse=True)

    if args.json:
        render.emit_json([course.to_dict() for course in courses])
        return 0
    if not courses:
        render.text("Sin cursos que coincidan con el filtro.")
        return 0

    periods = sorted({course.period for course in courses if course.period}, reverse=True)
    counted = f"{len(courses)} curso{'s' if len(courses) != 1 else ''}"
    plural = "periodo" if len(periods) == 1 else "periodos"
    render.text(ui.bold(f"{counted} · {plural} {', '.join(periods) or '-'}"))
    rows = [
        [
            index,
            course.period,
            course.name[:38],
            course.cycle,
            course.state[:12],
            course.enrollment[:18],
            course.group_id,
        ]
        for index, course in enumerate(courses, start=1)
    ]
    render.text()
    render.text(ui.table(
        ["#", "Periodo", "Curso", "Ciclo", "Estado", "Matricula", "nGruCodigo"],
        rows,
        max_widths=[3, 7, 38, 5, 12, 18, 10],
        aligns=["right", "left", "left", "right", "left", "left", "right"],
    ))
    render.text()
    render.text(ui.dim("Descargalo con: autonoma descargar <nGruCodigo> --seco"))
    return 0
