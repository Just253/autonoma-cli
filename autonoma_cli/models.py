"""Modelos normalizados de cursos y recursos del campus.

La API interna devuelve muchos campos y algunos cambian de nombre entre
versiones. Aqui se elige un subconjunto estable y se guarda el resto en
``raw`` por si hace falta depurar.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import quote, urljoin, urlparse

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

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACES = re.compile(r"\s+")
_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ", "aeiouAEIOUnNuU")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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


def slugify(text: str, *, limit: int = 70) -> str:
    """Convierte un titulo en un nombre seguro para archivos y carpetas."""

    text = clean_text(text).translate(_ACCENTS)
    text = _INVALID_FILENAME.sub("", text)
    text = re.sub(r"[^\w.\-]+", "_", text)
    text = _SPACES.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text[:limit].strip("._-") or "sin_titulo"


def safe_filename(text: str, *, fallback: str = "archivo", limit: int = 90) -> str:
    text = clean_text(text).translate(_ACCENTS)
    text = _INVALID_FILENAME.sub("", text)
    text = _SPACES.sub(" ", text).strip(" .")
    if not text:
        return fallback
    stem, extension = os.path.splitext(text)
    if len(text) > limit:
        text = stem[: max(1, limit - len(extension))].rstrip(" ._") + extension
    return text or fallback


def resolve_upload_url(base_url: str, url: Any) -> str:
    """Resuelve la URL real de un recurso.

    La API entrega tres formas:
      - nombre relativo a /uploads/  (``01-03-2027_..._DOCUMENTO.pdf``)
      - ruta absoluta al dominio     (``/UploadsEnvioEmailPDF/...pdf``)
      - URL completa                 (``https://...``)
    Algunos campos traen sufijos separados por ``||`` que hay que descartar.
    """

    text = clean_text(url).split("||")[0].strip()
    if not text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        return text
    if text.startswith("/"):
        return urljoin(base_url.rstrip("/") + "/", text.lstrip("/"))
    return f"{base_url.rstrip('/')}/uploads/{quote(text, safe='/')}"


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
class Course:
    group_id: int | str
    name: str
    code: str
    period: str
    cycle: str
    section: str
    group: str
    credits: str
    modality: str
    teacher: str
    teacher_email: str
    start_date: str
    end_date: str
    resources_count: int
    state: str
    syllabus_url: str
    raw: Mapping[str, Any] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    @classmethod
    def from_api(cls, data: Mapping[str, Any], base_url: str) -> "Course":
        teacher = " ".join(
            part
            for part in (
                clean_text(data.get("docenteNombre")),
                clean_text(data.get("docenteApellido")),
            )
            if part
        ) or clean_text(data.get("docente"))
        try:
            resources_count = int(clean_text(data.get("cantidadRecursos")) or 0)
        except ValueError:
            resources_count = 0
        syllabus = data.get("cSilabo") or ""
        return cls(
            group_id=data.get("nGruCodigo"),
            name=clean_text(data.get("asignatura")) or "Curso sin nombre",
            code=clean_text(data.get("codigo") or data.get("cCurDetCod")),
            period=clean_text(data.get("periodo")),
            cycle=clean_text(data.get("ciclo")),
            section=clean_text(data.get("seccion")),
            group=clean_text(data.get("grupo")),
            credits=clean_text(data.get("creditos")),
            modality=clean_text(data.get("modalidad")),
            teacher=teacher,
            teacher_email=clean_text(data.get("correoDocente")),
            start_date=clean_text(data.get("fechaInicioCurso")),
            end_date=clean_text(data.get("fechaFinCurso")),
            resources_count=resources_count,
            state="activo" if clean_text(data.get("EstadoCurso")) == "1" else "inactivo",
            syllabus_url=resolve_upload_url(base_url, syllabus) if syllabus else "",
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "name": self.name,
            "code": self.code,
            "period": self.period,
            "cycle": self.cycle,
            "section": self.section,
            "group": self.group,
            "credits": self.credits,
            "modality": self.modality,
            "teacher": self.teacher,
            "teacher_email": self.teacher_email,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "resources_count": self.resources_count,
            "state": self.state,
            "syllabus_url": self.syllabus_url,
        }

    def matches(self, token: str) -> bool:
        token = token.strip().lower()
        if not token:
            return False
        if token == str(self.group_id):
            return True
        haystack = " ".join(
            (self.name, self.code, self.group, self.section, self.period, self.teacher)
        ).lower()
        return token in haystack


@dataclass(frozen=True)
class SessionTopic:
    number: int
    label: str
    start_date: str
    end_date: str
    topic: str
    goal: str
    active: bool

    @property
    def title(self) -> str:
        first_line = (self.topic or "").splitlines()[0].strip()
        return first_line or f"Sesion {self.number:02d}"

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> "SessionTopic":
        try:
            number = int(clean_text(data.get("nSesion")) or 0)
        except ValueError:
            number = 0
        return cls(
            number=number,
            label=clean_text(data.get("cSesion")) or f"{number:02d}",
            start_date=clean_text(data.get("semana_fecha_inicio")),
            end_date=clean_text(data.get("semana_fecha_fin")),
            topic=clean_text(data.get("tema")),
            goal=clean_text(data.get("logro")),
            active=clean_text(data.get("sesion_activa")) == "1",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "label": self.label,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "topic": self.topic,
            "goal": self.goal,
            "active": self.active,
        }


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
