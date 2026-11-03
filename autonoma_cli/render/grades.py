"""Tablas y resumenes de notas."""

from __future__ import annotations

from typing import Sequence

from .. import ui
from ..models import AcademicSummary, Course, CourseGrades, HistoryCourse


def print_grades_summary(rows: Sequence[tuple[Course, CourseGrades]]) -> None:
    """Acumulado parcial de los cursos del periodo abierto."""

    print(
        ui.table(
            ["Curso", "Periodo", "Ciclo", "Acumulado", "Avance"],
            [
                [course.name, course.period, course.cycle, grades.average or "-",
                 f"{grades.percent}%"]
                for course, grades in rows
            ],
            max_widths=[42, 7, 5, 9, 6],
            aligns=["left", "left", "right", "right", "right"],
        )
    )


def print_closed_grades(rows: Sequence[HistoryCourse]) -> None:
    """Nota final (nPromocional) de los cursos de periodos cerrados."""

    print(
        ui.table(
            ["Periodo", "Ciclo", "Curso", "Cred.", "Nota"],
            [
                [row.period, row.cycle, row.name, row.credits or "-", row.grade or "-"]
                for row in rows
            ],
            max_widths=[7, 5, 42, 5, 5],
            aligns=["left", "right", "left", "right", "right"],
        )
    )


def print_grades_detail(course: Course, grades: CourseGrades) -> None:
    """Cabecera, criterios y acumulado de un curso del periodo abierto."""

    print(ui.bold(course.name))
    bits = [
        f"periodo {course.period}" if course.period else "",
        f"ciclo {course.cycle}" if course.cycle else "",
        f"grupo {course.group}" if course.group else "",
        f"{course.credits} creditos" if course.credits else "",
    ]
    print("  " + " · ".join(part for part in bits if part))
    print()
    if not grades.items:
        print("Sin criterios de evaluacion todavia.")
        return
    print(
        ui.table(
            ["Criterio", "Peso", "Nota", "Sesion", "Desde", "Hasta"],
            [
                [item.criterion, f"{item.weight:g}", item.grade, item.session,
                 item.start, item.end]
                for item in grades.items
            ],
            max_widths=[8, 5, 6, 6, 11, 11],
            aligns=["left", "right", "right", "right", "left", "left"],
        )
    )
    print()
    print(f"Acumulado {grades.average or '-'} / 20 (solo {grades.percent} % evaluado)")
    if grades.updated:
        print(ui.dim(f"Actualizado {grades.updated}"))


def print_closed_course(course: Course, grade: str) -> None:
    """Curso de un periodo cerrado: el campus no publica sus criterios."""

    print(ui.bold(course.name))
    bits = [
        f"periodo {course.period}" if course.period else "",
        f"ciclo {course.cycle}" if course.cycle else "",
    ]
    print("  " + " · ".join(part for part in bits if part))
    print()
    print(f"Nota final: {grade or '-'}")
    print(ui.dim("Periodo cerrado: el campus no publica criterios para cursos cerrados."))


def print_academic_summary(summary: AcademicSummary) -> None:
    """Promedio oficial del tablero, ponderado por creditos y por ciclo."""

    print()
    print(ui.bold("Promedio oficial"))
    rows = [
        ["Acumulado del tablero", f"{summary.accumulated:.2f}"],
        ["Calculado por creditos",
         f"{summary.weighted:.2f} ({summary.credits_weighted:g} creditos)"],
        ["Creditos", f"{summary.credits_approved:g} de {summary.credits_total:g} aprobados"],
        ["Merito", summary.merit or "-"],
    ]
    rows += [[f"Promedio {cycle.period}", f"{cycle.average:.2f}"] for cycle in summary.cycles]
    print(ui.table(["Dato", "Valor"], rows, max_widths=[24, 44]))
