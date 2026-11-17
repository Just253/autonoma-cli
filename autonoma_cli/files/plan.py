"""Plan de descarga: items, carpeta del curso y nombre de cada archivo.

La estructura destino es ``<out>/<curso>/Sesion_NN/<TIPO>_<titulo>.<ext>``: el
tipo va primero para que la carpeta se ordene sola y el titulo se recorta para
que el nombre entre en cualquier sistema de archivos.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..models import Course, Resource, kind_tag, slugify


@dataclass
class DownloadItem:
    """Un recurso con la ruta destino ya resuelta."""

    course: Course
    resource: Resource
    path: Path

    @property
    def label(self) -> str:
        return f"Sesion {self.resource.session_label} · {self.resource.title}"


def course_folder(course: Course) -> str:
    """Carpeta del curso: el nombre en slug, o el grupo si el slug queda vacio."""

    return slugify(f"{course.name}", limit=60) or f"curso_{course.group_id}"


def build_filename(resource: Resource) -> str:
    """``<TIPO>_<titulo>.<ext>`` con la extension que trae el recurso."""

    extension = resource.extension or ".bin"
    tag = kind_tag(resource.kind)
    title = slugify(resource.title, limit=80)
    return f"{tag}_{title}{extension}"


def plan_course(
    course: Course,
    sessions: Sequence[tuple[int, list[Resource]]],
    out_root: Path,
    *,
    kinds: set[int] | None = None,
    only: re.Pattern[str] | None = None,
    include_syllabus: bool = False,
) -> list[DownloadItem]:
    """Convierte (sesion, recursos) en rutas destino sin repetir nombres.

    Un recurso sin URL o una carpeta no se descargan; el silabo se salta salvo
    que se pida. Dos titulos iguales en la misma sesion se numeran ``(2)``,
    ``(3)`` en vez de pisarse.
    """

    base = out_root / course_folder(course)
    items: list[DownloadItem] = []
    used: set[Path] = set()

    for session, resources in sessions:
        for resource in resources:
            if not resource.downloadable:
                continue
            if kinds is not None and resource.kind not in kinds:
                continue
            if only is not None and not only.search(resource.title):
                continue
            if resource.kind == 0 and not include_syllabus:
                continue

            folder = base / f"Sesion_{session:02d}"
            target = folder / build_filename(resource)
            counter = 2
            while target in used:
                stem, suffix = os.path.splitext(target.name)
                target = folder / f"{stem} ({counter}){suffix}"
                counter += 1
            used.add(target)
            items.append(DownloadItem(course=course, resource=resource, path=target))

    return items
