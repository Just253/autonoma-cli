"""Cabecera de un curso y tabla del silabo."""

from __future__ import annotations

from typing import Sequence

from .. import ui
from ..models import Course, SessionTopic


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
