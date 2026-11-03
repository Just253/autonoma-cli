"""Modelos normalizados de cursos y recursos del campus.

La API interna devuelve muchos campos y algunos cambian de nombre entre
versiones. Aqui se elige un subconjunto estable y se guarda el resto en
``raw`` por si hace falta depurar.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote, urljoin, urlparse

from .errors import ProtocolError

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

# nTipo de la programacion -> modalidad visible
CLASS_KINDS: dict[int, str] = {
    0: "Sincrona",
    1: "Asincrona",
    2: "Presencial",
}

WEEKDAYS: tuple[str, ...] = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

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
_TIME_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*(?:a|al|hasta|–|-)\s*(\d{1,2}:\d{2})", re.I)

_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ", "aeiouAEIOUnNuU")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fold(text: Any) -> str:
    """Minusculas y sin acentos: comparar texto del campus sin pelearse."""

    return clean_text(text).translate(_ACCENTS).casefold()


_TAGS = re.compile(r"<[^>]+>")


def strip_html(value: Any) -> str:
    """Quita etiquetas y espacios sobrantes (el campus manda HTML en ``tipo``)."""

    return re.sub(r"\s+", " ", _TAGS.sub(" ", clean_text(value))).strip()


_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d")


def parse_date(value: Any) -> date | None:
    """Interpreta ``dd/mm/aaaa``, ``dd-mm-aaaa`` o ``aaaa-mm-dd``."""

    text = clean_text(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_float(value: Any) -> float | None:
    """Numero decimal del campus; vacio, ``"-"`` o basura devuelven None.

    Las notas llegan como texto con punto decimal (``"12.50"``) o como ``"-"``
    cuando el criterio todavia no esta calificado.
    """

    text = clean_text(value)
    if not text or text in {"-", "--"}:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    """Entero a partir del mismo texto tolerante de :func:`parse_float`."""

    number = parse_float(value)
    return int(number) if number is not None else None


def date_from_millis(value: Any) -> date | None:
    """Respaldo de ``fechaParse``: milisegundos desde epoch, en UTC."""

    try:
        millis = float(value)
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    try:
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None


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
    career: str = ""
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
            career=clean_text(data.get("carrera")),
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
            "career": self.career,
        }

    def matches(self, token: str) -> bool:
        token = token.strip().lower()
        if not token:
            return False
        if token == str(self.group_id):
            return True
        haystack = " ".join(
            (self.name, self.code, self.group, self.section, self.period, self.teacher, self.career)
        ).lower()
        return token in haystack


@dataclass(frozen=True)
class HistoryCourse:
    """Curso de un periodo cerrado, tal como lo devuelve el historial."""

    group_id: int | str
    name: str
    code: str
    period: str
    cycle: str
    section: str
    group: str
    credits: str
    teacher: str
    career: str
    state: str
    enrollment: str
    grade: str = ""
    grade_value: float | None = None
    raw: Mapping[str, Any] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> "HistoryCourse":
        grade = clean_text(data.get("nPromocional"))
        return cls(
            group_id=data.get("nGruCodigo"),
            name=clean_text(data.get("asignatura")) or "Curso sin nombre",
            code=clean_text(data.get("cCodigoAsignatura")),
            period=clean_text(data.get("cPeriodo")),
            cycle=clean_text(data.get("nCiclo")),
            section=clean_text(data.get("cSeccion")),
            group=clean_text(data.get("Grupo")),
            credits=clean_text(data.get("nNroCredito")),
            teacher=clean_text(data.get("docente")),
            career=clean_text(data.get("carrera")),
            state=clean_text(data.get("cEstado")),
            enrollment=clean_text(data.get("cTipo")),
            grade=grade,
            grade_value=parse_float(grade),
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
            "teacher": self.teacher,
            "career": self.career,
            "state": self.state,
            "enrollment": self.enrollment,
            "grade": self.grade,
        }

    def matches(self, token: str) -> bool:
        token = token.strip().lower()
        if not token:
            return False
        if token == str(self.group_id):
            return True
        haystack = " ".join(
            (self.name, self.code, self.group, self.section, self.period, self.teacher, self.career)
        ).lower()
        return token in haystack

    def to_course(self) -> "Course":
        """Adapta la fila del historial al modelo que usan los comandos."""

        return Course(
            group_id=self.group_id,
            name=self.name,
            code=self.code,
            period=self.period,
            cycle=self.cycle,
            section=self.section,
            group=self.group,
            credits=self.credits,
            modality="",
            teacher=self.teacher,
            teacher_email="",
            start_date="",
            end_date="",
            resources_count=0,
            state="activo" if fold(self.state) == "en proceso" else "inactivo",
            syllabus_url="",
            career=self.career,
            raw=self.raw,
        )


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
class ClassSession:
    """Una sesion programada: cuando, en que aula y de que curso."""

    group_id: int | str
    course: str
    number: int
    label: str
    topic: str
    date: str
    start_time: str
    end_time: str
    kind: str
    room: str
    code: int | str
    recorded: bool
    raw: Mapping[str, Any] = field(default=None, repr=False, compare=False)  # type: ignore[assignment]

    @property
    def title(self) -> str:
        first_line = (self.topic or "").splitlines()[0].strip()
        return first_line or f"Sesion {self.number:02d}"

    @property
    def date_value(self) -> date | None:
        return parse_date(self.date) or date_from_millis((self.raw or {}).get("fechaParse"))

    @property
    def time_range(self) -> str:
        if self.start_time and self.end_time:
            return f"{self.start_time}-{self.end_time}"
        return self.start_time or self.end_time

    def sort_key(self) -> tuple[date, str]:
        return (self.date_value or date.max, self.start_time)

    @classmethod
    def from_api(
        cls,
        data: Mapping[str, Any],
        *,
        group_id: int | str = "",
        course: str = "",
    ) -> "ClassSession":
        raw_date = clean_text(data.get("fecha"))
        day = parse_date(raw_date.split(" ")[0]) if raw_date else None
        if day is None:
            day = date_from_millis(data.get("fechaParse"))
        match = _TIME_RANGE.search(raw_date)
        start_time = match.group(1).zfill(5) if match else ""
        end_time = match.group(2).zfill(5) if match else ""
        try:
            number = int(clean_text(data.get("nSesion") or data.get("sesion")) or 0)
        except ValueError:
            number = 0
        kind = strip_html(data.get("tipo"))
        if not kind:
            try:
                kind = CLASS_KINDS.get(int(clean_text(data.get("nTipo")) or -1), "")
            except ValueError:
                kind = ""
        return cls(
            group_id=data.get("nGruCodigo") or group_id,
            course=clean_text(data.get("asignatura")) or course,
            number=number,
            label=clean_text(data.get("cSesion")) or f"{number:02d}",
            topic=clean_text(data.get("tema")),
            date=day.strftime("%d/%m/%Y") if day else raw_date.split(" ")[0],
            start_time=start_time,
            end_time=end_time,
            kind=kind,
            room=clean_text(data.get("ambiente")),
            code=data.get("nHorCodigo") or "",
            recorded=clean_text(data.get("nGrabacion")) == "1",
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        day = self.date_value
        return {
            "group_id": self.group_id,
            "course": self.course,
            "session": self.number,
            "session_label": self.label,
            "topic": self.topic,
            "date": day.isoformat() if day else self.date,
            "weekday": day.isoweekday() if day else None,
            "weekday_name": WEEKDAYS[day.weekday()] if day else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "time_range": self.time_range,
            "kind": self.kind,
            "room": self.room,
            "code": self.code,
            "recorded": self.recorded,
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


def _table(data: Mapping[str, Any], *keys: str) -> list[Mapping[str, Any]]:
    """Primera tabla presente en la respuesta, como lista de filas.

    ``cTablas`` pide nombres completos (``Malla_Curricular_grafAvanceCarrera``);
    se aceptan tambien los cortos por si el campus cambia la clave.
    """

    for key in keys:
        rows = data.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, Mapping)]
    return []


def _row(data: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    rows = _table(data, *keys)
    return rows[0] if rows else {}


@dataclass(frozen=True)
class GradeItem:
    """Un criterio de evaluacion del periodo en curso."""

    criterion: str
    weight: float
    grade: str
    value: float | None
    session: int
    start: str
    end: str

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> "GradeItem":
        grade = clean_text(data.get("nota"))
        return cls(
            criterion=clean_text(data.get("Criterio")),
            weight=parse_float(data.get("Peso")) or 0.0,
            grade=grade,
            value=parse_float(grade),
            session=parse_int(data.get("nSesion")) or 0,
            start=clean_text(data.get("cFechaInicio")),
            end=clean_text(data.get("cFechaFin")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "weight": self.weight,
            "grade": self.grade,
            "grade_value": self.value,
            "session": self.session,
            "from": self.start,
            "to": self.end,
        }


@dataclass(frozen=True)
class CourseGrades:
    """Criterios del periodo abierto; ``average`` es el acumulado, no un promedio."""

    group_id: int | str
    updated: str
    average: str
    average_value: float | None
    percent: int
    items: list[GradeItem]

    @classmethod
    def from_api(
        cls, data: Mapping[str, Any], *, group_id: int | str = ""
    ) -> "CourseGrades":
        total = clean_text(data.get("nPromTotal"))
        return cls(
            group_id=data.get("nGruCodigo") or group_id,
            updated=clean_text(data.get("fechaActualizado")),
            average=total,
            average_value=parse_float(total),
            percent=parse_int(data.get("porcentaje")) or 0,
            items=[GradeItem.from_api(row) for row in _table(data, "notas")],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "updated": self.updated,
            "average": self.average,
            "average_value": self.average_value,
            "percent": self.percent,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class CycleAverage:
    """Promedio del ciclo tal como lo dibuja el tablero."""

    period: str
    average: float

    def to_dict(self) -> dict[str, Any]:
        return {"period": self.period, "average": self.average}


def _weighted(malla: list[Mapping[str, Any]]) -> tuple[float, float]:
    """Promedio ponderado por creditos de la malla y sus creditos.

    Solo entran los cursos con ``Nota > 0``: un curso sin nota no baja el
    promedio. La ``Nota`` viene redondeada, asi que puede diferir en centesimas
    del promedio oficial del tablero.
    """

    weighted = 0.0
    credits = 0.0
    for row in malla:
        note = parse_float(row.get("Nota"))
        credit = parse_float(row.get("nNroCredito"))
        if note is None or note <= 0 or not credit:
            continue
        weighted += note * credit
        credits += credit
    return (round(weighted / credits, 2) if credits else 0.0, credits)


def _merit(data: Mapping[str, Any], malla: list[Mapping[str, Any]]) -> Any:
    """``perMerito`` aparece en la malla, en la ficha o en la raiz."""

    for source in (malla[0] if malla else {}, data, _row(data, "DatosPersonales")):
        value = source.get("perMerito")
        if value not in (None, ""):
            return value
    return None


@dataclass(frozen=True)
class AcademicSummary:
    """Promedio oficial del tablero y el ponderado por creditos de la malla."""

    accumulated: float
    weighted: float
    credits_weighted: float
    credits_total: float
    credits_approved: float
    merit: int
    cycles: list[CycleAverage]

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> "AcademicSummary":
        malla = _table(data, "Malla_Curricular", "MALLA_CURRICULAR")
        advance = _row(
            data, "Malla_Curricular_grafAvanceCarrera", "grafAvanceCarrera"
        )
        weighted, credits_weighted = _weighted(malla)
        official = parse_float((malla[0] if malla else {}).get("nPromedioAcumulado"))
        cycles: list[CycleAverage] = []
        graph = _table(
            data,
            "Malla_Curricular_grafPromedioNotaByCiclo",
            "grafPromedioNotaByCiclo",
        )
        for row in graph:
            average = parse_float(row.get("promedioPorCiclo"))
            if average is None:
                continue
            cycles.append(CycleAverage(clean_text(row.get("Periodo")), average))
        if official is None:
            raise ProtocolError("El tablero no devolvio el promedio acumulado.")
        return cls(
            accumulated=official,
            weighted=weighted,
            credits_weighted=credits_weighted,
            credits_total=parse_float(advance.get("totalCreditos")) or 0.0,
            credits_approved=parse_float(advance.get("totalCreditosAprobados")) or 0.0,
            merit=parse_int(_merit(data, malla)) or 0,
            cycles=cycles,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "accumulated": self.accumulated,
            "weighted": self.weighted,
            "credits_weighted": self.credits_weighted,
            "credits_total": self.credits_total,
            "credits_approved": self.credits_approved,
            "merit": self.merit,
            "cycles": [cycle.to_dict() for cycle in self.cycles],
        }
