"""Plan y descarga de archivos: `descargar` y `todo`."""

from __future__ import annotations

import argparse
import re
from typing import Sequence

from .. import config, render, selectors, ui
from ..client import CampusClient
from ..downloader import DownloadItem, Manifest, plan_course, run_plan
from ..errors import UsageError
from ..models import Course
from .base import out_dir
from .data import _resources_of, catalog


def _plan(args: argparse.Namespace, client: CampusClient, course: Course) -> list[DownloadItem]:
    sessions = selectors.parse_sessions(args.sesion)
    grouped = _resources_of(client, course, sessions)
    pattern = re.compile(args.solo, re.I) if args.solo else None
    return plan_course(
        course,
        grouped,
        out_dir(args),
        kinds=selectors.kind_filter(args.tipo),
        only=pattern,
        include_syllabus=args.incluir_silabo,
    )


def _download(args: argparse.Namespace, client: CampusClient, courses: Sequence[Course]) -> int:
    root = out_dir(args)
    root.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(root)
    all_items: list[DownloadItem] = []

    for course in courses:
        render.text()
        render.print_course_header(course)
        items = _plan(args, client, course)
        all_items.extend(items)
        if not items:
            render.text(ui.yellow("  Sin archivos que coincidan con el filtro."))

    if not all_items:
        render.text("\nNada que descargar.")
        return 0

    if args.seco:
        render.text()
        render.text(ui.table(
            ["Curso", "Ses.", "Tipo", "Archivo"],
            [
                [
                    item.course.name[:28],
                    item.resource.session_label,
                    item.resource.kind_name,
                    str(item.path.relative_to(root)),
                ]
                for item in all_items
            ],
            max_widths=[28, 4, 11, 90],
        ))
        render.text(f"\n{len(all_items)} archivos · destino {root} (simulacion, nada descargado)")
        return 0

    render.text(f"\nDescargando {len(all_items)} archivos → {root}")
    stats = run_plan(
        all_items,
        manifest,
        cookie_header=client.cookie_header(),
        timeout=client.timeout,
        workers=args.workers if args.workers is not None else config.load_settings().workers,
        force=args.forzar,
        referer=client.referer,
        on_event=render.progress,
    )
    render.print_stats(stats)
    if args.json:
        render.emit_json(
            {
                "downloaded": stats.downloaded,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "bytes": stats.bytes,
                "out": str(root),
                "failures": stats.failures,
            }
        )
    return 0 if stats.failed == 0 else 1


def run_descargar(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    course = selectors.resolve_course(courses, args.curso)
    return _download(args, client, [course])


def run_todo(client: CampusClient, args: argparse.Namespace) -> int:
    courses = selectors.filter_courses(
        catalog(client, refresh=args.refresh),
        cycle=args.ciclo,
        period=args.periodo,
        career=args.carrera,
        active=args.activos,
    )
    if args.curso:
        courses = [course for course in courses if course.matches(args.curso)]
        if not courses:
            raise UsageError(f"No hay cursos que coincidan con {args.curso!r}.")
    if not courses:
        raise UsageError("No hay cursos que coincidan con --ciclo/--periodo/--carrera/--activos.")
    return _download(args, client, courses)
