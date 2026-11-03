"""Datos ficticios compartidos por los tests de la CLI."""

from __future__ import annotations

from autonoma_cli.models import Course

BASE = "https://virtual.autonoma.edu.pe"


def courses() -> list[Course]:
    return [
        Course.from_api({"nGruCodigo": 90000001, "asignatura": "CURSO DE EJEMPLO UNO", "codigo": "PISOP00001"}, BASE),
        Course.from_api({"nGruCodigo": 90000002, "asignatura": "CURSO DE EJEMPLO DOS", "codigo": "PISOP00002"}, BASE),
    ]


def mixed_courses() -> list[Course]:
    """Tres cursos: dos periodos, dos carreras, uno inactivo."""

    return [
        Course.from_api(
            {
                "nGruCodigo": 90000001,
                "asignatura": "CURSO DE EJEMPLO UNO",
                "periodo": "209901",
                "ciclo": "8",
                "carrera": "INGENIERÍA DE EJEMPLO",
                "EstadoCurso": "1",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000002,
                "asignatura": "CURSO DE EJEMPLO DOS",
                "periodo": "209802",
                "ciclo": "2",
                "carrera": "INGENIERÍA DE EJEMPLO",
                "EstadoCurso": "2",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000003,
                "asignatura": "CURSO DE EJEMPLO TRES",
                "periodo": "209901",
                "ciclo": "2",
                "carrera": "ADMINISTRACIÓN DE EJEMPLO",
                "EstadoCurso": "1",
            },
            BASE,
        ),
    ]
