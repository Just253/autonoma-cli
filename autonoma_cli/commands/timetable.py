"""Comando `horario`: fechas, horas y aulas."""

from __future__ import annotations

import argparse

from .. import render, selectors, ui
from ..client import CampusClient
from .data import catalog, resolve_any, schedule


def run_horario(client: CampusClient, args: argparse.Namespace) -> int:
    start, end = selectors.schedule_range(args)
    courses = selectors.filter_courses(
        catalog(client, refresh=args.refresh),
        cycle=args.ciclo,
        period=args.periodo,
        career=args.carrera,
        active=args.activos,
    )
    if not courses:
        if args.json:
            render.emit_json(
                {
                    "from": start.isoformat() if start else None,
                    "to": end.isoformat() if end else None,
                    "count": 0,
                    "sessions": [],
                }
            )
        else:
            render.text("Sin cursos que coincidan con el filtro.")
        return 0
    if args.curso:
        courses = [resolve_any(client, courses, args.curso, refresh=args.refresh)]
    else:
        active = [course for course in courses if course.state == "activo"]
        courses = active or courses
    entries = schedule(client, courses, refresh=args.refresh)

    if start is not None and end is not None:
        entries = [
            entry
            for entry in entries
            if entry.date_value is not None and start <= entry.date_value <= end
        ]
    entries.sort(key=lambda entry: entry.sort_key())

    if args.json:
        render.emit_json(
            {
                "from": start.isoformat() if start else None,
                "to": end.isoformat() if end else None,
                "count": len(entries),
                "sessions": [entry.to_dict() for entry in entries],
            }
        )
        return 0

    render.print_schedule(entries, start, end)
    render.text()
    render.text(ui.dim("Opciones: --hoy | --manana | --dia dd/mm/aaaa | --desde/--hasta | --todo"))
    return 0
