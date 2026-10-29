"""Salida de la CLI: JSON y tablas en la terminal."""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any, Sequence

from . import ui
from .downloader import DownloadItem, human_size
from .models import ClassSession, Course, Resource, SessionTopic, WEEKDAYS


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def print_course_header(course: Course) -> None:
    print(ui.bold(course.name))
    details = [
        f"{course.code}" if course.code else "",
        f"periodo {course.period}" if course.period else "",
        f"ciclo {course.cycle}" if course.cycle else "",
        f"grupo {course.group}",
        f"{course.credits} creditos" if course.credits else "",
        course.modality,
    ]
    print("  " + " · ".join(part for part in details if part))
    if course.teacher:
        contact = f" <{course.teacher_email}>" if course.teacher_email else ""
        print(f"  Docente: {course.teacher}{contact}")
    if course.start_date or course.end_date:
        print(f"  Periodo de clases: {course.start_date} → {course.end_date}")
    print(f"  nGruCodigo: {course.group_id} · recursos: {course.resources_count}")


def print_syllabus(topics: Sequence[SessionTopic]) -> None:
    rows = []
    for topic in topics:
        first_line = (topic.topic or "").splitlines()[0]
        rows.append(
            [
                topic.label,
                f"{topic.start_date} - {topic.end_date}",
                first_line[:70],
                "*" if topic.active else "",
            ]
        )
    print()
    print(ui.table(["Ses.", "Semana", "Tema", "Act."], rows, max_widths=[5, 23, 70, 4]))


def session_count(count: int) -> str:
    return f"{count} sesion" if count == 1 else f"{count} sesiones"


def print_schedule(
    entries: Sequence[ClassSession],
    start: dt.date | None,
    end: dt.date | None,
) -> None:
    today = dt.date.today()
    if start is None or end is None:
        heading = f"Horario completo · {session_count(len(entries))}"
    elif start == end:
        label = "Hoy" if start == today else WEEKDAYS[start.weekday()].capitalize()
        heading = f"{label}, {start:%d/%m/%Y}"
        if entries:
            heading += f" · {session_count(len(entries))}"
    else:
        heading = f"Del {start:%d/%m/%Y} al {end:%d/%m/%Y} · {session_count(len(entries))}"
    print(ui.bold(heading))

    if not entries:
        where = "para esa fecha" if start == end else "en ese rango"
        if start is None or end is None:
            where = "en el periodo"
        print(ui.yellow(f"Sin clases {where}."))
        return

    grouped: list[tuple[dt.date, list[ClassSession]]] = []
    for entry in entries:
        day = entry.date_value
        if day is None:
            continue
        if grouped and grouped[-1][0] == day:
            grouped[-1][1].append(entry)
        else:
            grouped.append((day, [entry]))

    for day, items in grouped:
        print()
        print(ui.bold(f"{WEEKDAYS[day.weekday()].capitalize()} {day:%d/%m/%Y}"))
        rows = [
            [
                entry.time_range or "-",
                entry.course,
                entry.room or "-",
                entry.kind or "-",
                entry.label,
            ]
            for entry in items
        ]
        print(
            ui.table(
                ["Hora", "Curso", "Aula", "Tipo", "Ses."],
                rows,
                max_widths=[13, 46, 32, 12, 4],
            )
        )

    if start is not None and start == end:
        print()
        for entry in entries:
            print(ui.dim(f"  {entry.label} · {entry.title[:96]}"))


def resource_rows(resources: Sequence[Resource]) -> list[list[str]]:
    return [
        [
            resource.session_label,
            resource.kind_name,
            resource.title[:60],
            resource.extension.lstrip(".") or "-",
            resource.date,
        ]
        for resource in resources
    ]


def progress(kind: str, item: DownloadItem, detail: str) -> None:
    label = f"S{int(item.resource.session):02d} · {item.resource.title[:64]}"
    if kind == "done":
        print(f"  {ui.green('[ok]')}   {label} ({detail})")
    elif kind == "skip":
        print(f"  {ui.dim('[igual]')} {label}")
    elif kind == "error":
        print(f"  {ui.red('[error]')} {label}: {detail}", file=sys.stderr)


def print_stats(stats: Any, dry_run: bool = False) -> None:
    if dry_run:
        return
    print()
    print(
        f"Descargados: {stats.downloaded} · Ya estaban: {stats.skipped} · "
        f"Errores: {stats.failed} · Total: {human_size(stats.bytes)}"
    )
    for path, message in stats.failures:
        print(f"  {ui.red('x')} {path}: {message}", file=sys.stderr)
