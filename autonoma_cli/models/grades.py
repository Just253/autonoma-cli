"""Notas del periodo, criterios de evaluacion y resumen academico."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..errors import ProtocolError
from .common import clean_text, parse_float, parse_int


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
