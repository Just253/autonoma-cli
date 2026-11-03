"""Datos y cliente de mentira compartidos por los tests de `autonoma notas`."""

from __future__ import annotations

import argparse

from autonoma_cli.models import AcademicSummary, Course, CourseGrades

BASE = "https://virtual.autonoma.edu.pe"


def courses() -> list[Course]:
    return [
        Course.from_api(
            {
                "nGruCodigo": 90000001,
                "asignatura": "CURSO DE EJEMPLO UNO",
                "codigo": "PISOP00001",
                "periodo": "209901",
                "ciclo": "8",
                "grupo": "1T1",
                "creditos": "3",
                "EstadoCurso": "1",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000002,
                "asignatura": "CURSO DE EJEMPLO DOS",
                "codigo": "PISOP00002",
                "periodo": "209901",
                "ciclo": "8",
                "grupo": "1T1",
                "creditos": "4",
                "EstadoCurso": "1",
            },
            BASE,
        ),
        Course.from_api(
            {
                "nGruCodigo": 90000003,
                "asignatura": "CURSO DE EJEMPLO TRES",
                "codigo": "PISOP00003",
                "periodo": "209901",
                "ciclo": "8",
                "grupo": "1T1",
                "creditos": "3",
                "EstadoCurso": "2",
            },
            BASE,
        ),
    ]


HISTORY_ROWS = [
    {
        "nGruCodigo": 90000011,
        "asignatura": "CURSO HISTORICO UNO",
        "cCodigoAsignatura": "EJEM0001",
        "cPeriodo": "209802",
        "nCiclo": 7,
        "cEstado": "APROBADA",
        "cTipo": "MATRICULA REGULAR",
        "carrera": "INGENIERÍA DE EJEMPLO",
        "Grupo": "1T1",
        "nNroCredito": 3,
        "docente": "DOCENTE DE EJEMPLO",
        "nPromocional": 15,
    },
    {
        # Mismo grupo que el catalogo activo: no debe repetirse en el historico.
        "nGruCodigo": 90000001,
        "asignatura": "CURSO DE EJEMPLO UNO",
        "cPeriodo": "209901",
        "nCiclo": 8,
        "cEstado": "EN PROCESO",
        "nNroCredito": 3,
        "nPromocional": 9,
    },
]

GRADES_RAW = {
    "90000001": {
        "fechaActualizado": "02/11/2027 20:30:30",
        "nPromTotal": "9.6",
        "porcentaje": "67",
        "notas": [
            {"Criterio": "EC", "Peso": "10", "nota": "20.00", "nSesion": 4,
             "cFechaInicio": "25/09/2027", "cFechaFin": "27/09/2027"},
            {"Criterio": "EP", "Peso": "40", "nota": "19.00", "nSesion": 8,
             "cFechaInicio": "23/10/2027", "cFechaFin": "25/10/2027"},
            {"Criterio": "EF", "Peso": "50", "nota": "-", "nSesion": 16,
             "cFechaInicio": "18/12/2027", "cFechaFin": "19/12/2027"},
        ],
    },
    "90000002": {
        "fechaActualizado": "02/11/2027 20:30:30",
        "nPromTotal": "0",
        "porcentaje": "0",
        "notas": [],
    },
}

SUMMARY_RAW = {
    "Malla_Curricular": [
        {"Nota": 16, "nNroCredito": 3, "nPromedioAcumulado": 15.23, "perMerito": 12},
        {"Nota": 14, "nNroCredito": 4, "nPromedioAcumulado": 15.23, "perMerito": 12},
        {"Nota": 0, "nNroCredito": 3, "nPromedioAcumulado": 15.23, "perMerito": 12},
    ],
    "Malla_Curricular_grafAvanceCarrera": [
        {"totalCreditos": 135, "totalCreditosAprobados": 120},
    ],
    "Malla_Curricular_grafPromedioNotaByCiclo": [
        {"Periodo": "209801", "promedioPorCiclo": 14.5},
        {"Periodo": "209802", "promedioPorCiclo": 15.75},
    ],
}


class FakeGradesApi:
    """Cliente de mentira: mismas firmas que usa run_notas, sin red."""

    base_url = BASE
    student_code = "2024000001"

    def __init__(self) -> None:
        self.grade_calls: list[str] = []
        self.summary_calls = 0

    def get_courses(self) -> list[Course]:
        return courses()

    def get_history(self) -> list[dict[str, object]]:
        return [dict(row) for row in HISTORY_ROWS]

    def get_grades(self, group_id: int | str) -> CourseGrades:
        self.grade_calls.append(str(group_id))
        raw = GRADES_RAW.get(str(group_id), {"notas": []})
        return CourseGrades.from_api(raw, group_id=group_id)

    def get_academic_summary(self) -> AcademicSummary:
        self.summary_calls += 1
        return AcademicSummary.from_api(SUMMARY_RAW)


def notas_args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "curso": None,
        "todos": False,
        "activos": False,
        "periodo": None,
        "ciclo": None,
        "carrera": None,
        "promedio": False,
        "refresh": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)
