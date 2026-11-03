"""Sesiones programadas y temas de la ruta de aprendizaje."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

from .common import clean_text, date_from_millis, parse_date, strip_html

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

_TIME_RANGE = re.compile(r"(\d{1,2}:\d{2})\s*(?:a|al|hasta|–|-)\s*(\d{1,2}:\d{2})", re.I)


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
