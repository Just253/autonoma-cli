"""Salida de la CLI: JSON y tablas en la terminal.

El paquete se parte por tema; este ``__init__`` reexporta la misma API
publica que tenia ``render.py`` para que ``from .. import render`` y
``render.text(...)`` sigan funcionando igual.
"""

from __future__ import annotations

from .text import emit_json, text
from .courses import print_course_header, print_syllabus
from .schedule import print_schedule, session_count
from .resources import resource_rows
from .downloads import print_stats, progress
from .grades import (
    print_academic_summary,
    print_closed_course,
    print_closed_grades,
    print_grades_detail,
    print_grades_summary,
)

__all__ = [
    "emit_json",
    "text",
    "print_course_header",
    "print_syllabus",
    "print_schedule",
    "session_count",
    "resource_rows",
    "print_stats",
    "progress",
    "print_academic_summary",
    "print_closed_course",
    "print_closed_grades",
    "print_grades_detail",
    "print_grades_summary",
]
