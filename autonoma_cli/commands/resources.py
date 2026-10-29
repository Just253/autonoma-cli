"""Comando `recursos`: recursos de un curso por sesion."""

from __future__ import annotations

import argparse

from .. import render, selectors, ui
from ..client import CampusClient
from .data import _resources_of, catalog


def run_recursos(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    course = selectors.resolve_course(courses, args.curso)
    sessions = selectors.parse_sessions(args.sesion)
    grouped = _resources_of(client, course, sessions)

    flat = [item for _, resources in grouped for item in resources]
    if args.json:
        render.emit_json({"course": course.to_dict(), "resources": [item.to_dict() for item in flat]})
        return 0

    render.print_course_header(course)
    total = 0
    for session, resources in grouped:
        label = f"Sesion {session:02d}"
        if not resources:
            render.text(ui.dim(f"\n{label} · sin recursos"))
            continue
        render.text(f"\n{ui.bold(label)} · {len(resources)} recursos")
        render.text(ui.table(
            ["Ses.", "Tipo", "Titulo", "Ext", "Fecha"],
            render.resource_rows(resources),
            max_widths=[4, 11, 60, 5, 10],
        ))
        total += len(resources)
    render.text()
    render.text(f"Total: {total} recursos en {len([1 for _, items in grouped if items])} sesiones.")
    render.text(ui.dim(f"Descargar: autonoma descargar {course.group_id} --tipo archivo"))
    return 0
