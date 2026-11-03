"""Salida de la CLI: JSON y tablas en la terminal."""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Any, Sequence

from . import ui
from .downloader import DownloadItem, human_size
from .models import (
    WEEKDAYS,
    AcademicSummary,
    ClassSession,
    Course,
    CourseGrades,
    HistoryCourse,
    Resource,
    SessionTopic,
)


def text(message: object = "", *, stream: Any = None) -> None:
    """Escribe una linea. Unico punto de salida de texto de los comandos."""

    print(message, file=sys.stdout if stream is None else stream)


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
    if course.state and course.state != "activo":
        details.append(course.state)
    print("  " + " · ".join(part for part in details if part))
    if course.career:
        print(f"  Carrera: {course.career}")
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


# --------------------------------------------------------------------------- #
# Notas
# --------------------------------------------------------------------------- #


def print_grades_summary(rows: Sequence[tuple[Course, CourseGrades]]) -> None:
    """Acumulado parcial de los cursos del periodo abierto."""

    print(
        ui.table(
            ["Curso", "Periodo", "Ciclo", "Acumulado", "Avance"],
            [
                [course.name, course.period, course.cycle, grades.average or "-",
                 f"{grades.percent}%"]
                for course, grades in rows
            ],
            max_widths=[42, 7, 5, 9, 6],
            aligns=["left", "left", "right", "right", "right"],
        )
    )


def print_closed_grades(rows: Sequence[HistoryCourse]) -> None:
    """Nota final (nPromocional) de los cursos de periodos cerrados."""

    print(
        ui.table(
            ["Periodo", "Ciclo", "Curso", "Cred.", "Nota"],
            [
                [row.period, row.cycle, row.name, row.credits or "-", row.grade or "-"]
                for row in rows
            ],
            max_widths=[7, 5, 42, 5, 5],
            aligns=["left", "right", "left", "right", "right"],
        )
    )


def print_grades_detail(course: Course, grades: CourseGrades) -> None:
    """Cabecera, criterios y acumulado de un curso del periodo abierto."""

    print(ui.bold(course.name))
    bits = [
        f"periodo {course.period}" if course.period else "",
        f"ciclo {course.cycle}" if course.cycle else "",
        f"grupo {course.group}" if course.group else "",
        f"{course.credits} creditos" if course.credits else "",
    ]
    print("  " + " · ".join(part for part in bits if part))
    print()
    if not grades.items:
        print("Sin criterios de evaluacion todavia.")
        return
    print(
        ui.table(
            ["Criterio", "Peso", "Nota", "Sesion", "Desde", "Hasta"],
            [
                [item.criterion, f"{item.weight:g}", item.grade, item.session,
                 item.start, item.end]
                for item in grades.items
            ],
            max_widths=[8, 5, 6, 6, 11, 11],
            aligns=["left", "right", "right", "right", "left", "left"],
        )
    )
    print()
    print(f"Acumulado {grades.average or '-'} / 20 (solo {grades.percent} % evaluado)")
    if grades.updated:
        print(ui.dim(f"Actualizado {grades.updated}"))


def print_closed_course(course: Course, grade: str) -> None:
    """Curso de un periodo cerrado: el campus no publica sus criterios."""

    print(ui.bold(course.name))
    bits = [
        f"periodo {course.period}" if course.period else "",
        f"ciclo {course.cycle}" if course.cycle else "",
    ]
    print("  " + " · ".join(part for part in bits if part))
    print()
    print(f"Nota final: {grade or '-'}")
    print(ui.dim("Periodo cerrado: el campus no publica criterios para cursos cerrados."))


def print_academic_summary(summary: AcademicSummary) -> None:
    """Promedio oficial del tablero, ponderado por creditos y por ciclo."""

    print()
    print(ui.bold("Promedio oficial"))
    rows = [
        ["Acumulado del tablero", f"{summary.accumulated:.2f}"],
        ["Calculado por creditos",
         f"{summary.weighted:.2f} ({summary.credits_weighted:g} creditos)"],
        ["Creditos", f"{summary.credits_approved:g} de {summary.credits_total:g} aprobados"],
        ["Merito", summary.merit or "-"],
    ]
    rows += [[f"Promedio {cycle.period}", f"{cycle.average:.2f}"] for cycle in summary.cycles]
    print(ui.table(["Dato", "Valor"], rows, max_widths=[24, 44]))
