"""Cursos del periodo en curso y del historial academico."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .common import clean_text, fold, parse_float, resolve_upload_url


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
