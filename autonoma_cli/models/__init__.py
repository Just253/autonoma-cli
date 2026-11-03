"""Modelos normalizados de cursos y recursos del campus.

La API interna devuelve muchos campos y algunos cambian de nombre entre
versiones. Aca se elige un subconjunto estable y se guarda el resto en
``raw`` por si hace falta depurar.

El paquete se parte por dominio; este ``__init__`` reexporta la misma API
publica que tenia ``models.py`` para que ningun import externo cambie.
"""

from __future__ import annotations

from .common import (
    clean_text,
    date_from_millis,
    fold,
    parse_date,
    parse_float,
    parse_int,
    resolve_upload_url,
    safe_filename,
    slugify,
    strip_html,
)
from .courses import Course, HistoryCourse
from .resources import (
    EXTENSION_BY_ICON,
    ITINERARY,
    RESOURCE_KINDS,
    Resource,
    extension_from,
    itinerary_name,
    kind_name,
    kind_tag,
)
from .sessions import CLASS_KINDS, WEEKDAYS, ClassSession, SessionTopic
from .grades import (
    AcademicSummary,
    CourseGrades,
    CycleAverage,
    GradeItem,
)

__all__ = [
    "clean_text",
    "date_from_millis",
    "fold",
    "parse_date",
    "parse_float",
    "parse_int",
    "resolve_upload_url",
    "safe_filename",
    "slugify",
    "strip_html",
    "Course",
    "HistoryCourse",
    "EXTENSION_BY_ICON",
    "ITINERARY",
    "RESOURCE_KINDS",
    "Resource",
    "extension_from",
    "itinerary_name",
    "kind_name",
    "kind_tag",
    "CLASS_KINDS",
    "WEEKDAYS",
    "ClassSession",
    "SessionTopic",
    "AcademicSummary",
    "CourseGrades",
    "CycleAverage",
    "GradeItem",
]
