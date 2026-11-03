"""Recursos de una sesion: tipo, enlace, extension e itinerario."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

from .common import _ACCENTS, clean_text, resolve_upload_url

# nDocLinTipo -> nombre visible
RESOURCE_KINDS: dict[int, str] = {
    0: "Silabo",
    1: "Carpeta",
    2: "Archivo",
    3: "Enlace",
    4: "Tarea",
    5: "Evaluacion",
    6: "Cuestionario",
    7: "Foro",
    8: "Wiki",
    9: "Reunion",
    10: "SCORM",
}

# nItinerario -> momento de la ruta de aprendizaje
ITINERARY: dict[int, str] = {
    1: "INDAGA",
    2: "INTERIORIZA",
    3: "INTEGRA",
}

# Icono FontAwesome del campus -> extension probable
EXTENSION_BY_ICON: dict[str, str] = {
    "fa-file-pdf": ".pdf",
    "fa-file-word": ".docx",
    "fa-file-excel": ".xlsx",
    "fa-file-powerpoint": ".pptx",
    "fa-file-image": ".png",
    "fa-file-video": ".mp4",
    "fa-file-audio": ".mp3",
    "fa-file-zipper": ".zip",
    "fa-file-archive": ".zip",
    "fa-file-code": ".txt",
    "fa-file-lines": ".txt",
    "fa-file": ".bin",
}


def kind_name(kind: Any) -> str:
    try:
        number = int(kind)
    except (TypeError, ValueError):
        return "Otro"
    return RESOURCE_KINDS.get(number, f"Otro ({number})")


def kind_tag(kind: Any) -> str:
    """Etiqueta corta y sin acentos para nombres de archivo."""

    return kind_name(kind).translate(_ACCENTS).upper()


def itinerary_name(value: Any) -> str:
    try:
        return ITINERARY.get(int(value), "")
    except (TypeError, ValueError):
        return ""


def extension_from(url: str, icon: str = "") -> str:
    path = urlparse(url).path
    extension = os.path.splitext(path)[1].lower()
    if extension and len(extension) <= 8:
        return extension
    for key, value in EXTENSION_BY_ICON.items():
        if icon and key in icon:
            return value
    return ""


@dataclass(frozen=True)
class Resource:
    title: str
    kind: int
    kind_name: str
    resource_id: str
    session: int
    session_label: str
    url: str
    extension: str
    date: str
    itinerary: str
    description: str
    raw: Mapping[str, Any] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    @classmethod
    def from_api(
        cls,
        data: Mapping[str, Any],
        base_url: str,
        *,
        session: int | None = None,
    ) -> "Resource":
        raw_url = clean_text(data.get("url"))
        absolute = resolve_upload_url(base_url, raw_url)
        try:
            kind = int(clean_text(data.get("nDocLinTipo")) or 0)
        except ValueError:
            kind = 0
        try:
            number = int(clean_text(data.get("nSesion")) or session or 0)
        except ValueError:
            number = session or 0
        return cls(
            title=clean_text(data.get("cTitulo")) or "(sin titulo)",
            kind=kind,
            kind_name=kind_name(kind),
            resource_id=clean_text(data.get("nDocLinNum")),
            session=number,
            session_label=clean_text(data.get("cSesion")) or f"{number:02d}",
            url=absolute,
            extension=extension_from(absolute, clean_text(data.get("clase"))),
            date=clean_text(data.get("dDocTraFec")),
            itinerary=itinerary_name(data.get("nItinerario")),
            description=clean_text(data.get("descripcion")),
            raw=data,
        )

    @property
    def downloadable(self) -> bool:
        return bool(self.url) and self.kind != 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "kind": self.kind,
            "kind_name": self.kind_name,
            "resource_id": self.resource_id,
            "session": self.session,
            "session_label": self.session_label,
            "url": self.url,
            "extension": self.extension,
            "date": self.date,
            "itinerary": self.itinerary,
            "description": self.description,
        }
