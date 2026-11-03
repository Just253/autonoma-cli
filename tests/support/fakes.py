"""Clientes de mentira compartidos por mas de un archivo de tests."""

from __future__ import annotations

from autonoma_cli.models import ClassSession, Course

from .fixtures import BASE, courses

# Registros crudos tal como los devuelve getProgramacionAlumnoGrupo.
SCHEDULE_RECORDS: dict[str, list[dict[str, object]]] = {
    "90000001": [
        {
            "nSesion": 1,
            "cSesion": "01",
            "tema": "Introduccion a la materia",
            "fecha": "03/11/2026 08:00 a 10:00",
            "tipo": "Presencial",
            "ambiente": "B-202 (Aula)",
        },
        {
            "nSesion": 2,
            "cSesion": "02",
            "tema": "Practica de laboratorio",
            "fecha": "05/11/2026 14:00 a 16:00",
            "tipo": "Presencial",
            "ambiente": "A-101 (Laboratorio)",
        },
        {
            "nSesion": 3,
            "cSesion": "03",
            "tema": "Clase posterior al rango",
            "fecha": "10/11/2026 09:00 a 11:00",
            "tipo": "Presencial",
            "ambiente": "B-202 (Aula)",
        },
    ],
    "90000002": [
        {
            "nSesion": 1,
            "cSesion": "01",
            "tema": "Seminario de repaso",
            "fecha": "05/11/2026 08:00 a 10:00",
            "tipo": "Sincrona",
            "ambiente": "C-303 (Aula)",
        },
        {
            "nSesion": 2,
            "cSesion": "02",
            "tema": "Clase anterior al rango",
            "fecha": "01/11/2026 07:00 a 09:00",
            "tipo": "Sincrona",
            "ambiente": "C-303 (Aula)",
        },
    ],
}


class FakeCampusClient:
    """Cliente de mentira: mismas firmas que usa run_horario, sin red."""

    base_url = BASE
    student_code = "2024000001"

    def __init__(self) -> None:
        self.schedule_calls: list[tuple[object, str]] = []

    def get_courses(self) -> list[Course]:
        return courses()

    def get_schedule(self, group_id: int | str, *, course: str = "") -> list[ClassSession]:
        self.schedule_calls.append((group_id, course))
        records = SCHEDULE_RECORDS.get(str(group_id), [])
        return [
            ClassSession.from_api(record, group_id=group_id, course=course)
            for record in records
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
    },
    {
        "nGruCodigo": 90000012,
        "asignatura": "CURSO HISTORICO DOS",
        "cCodigoAsignatura": "EJEM0002",
        "cPeriodo": "209901",
        "nCiclo": 8,
        "cEstado": "EN PROCESO",
        "cTipo": "MATRICULA REGULAR",
        "carrera": "INGENIERÍA DE EJEMPLO",
        "Grupo": "2T1",
        "nNroCredito": 3,
        "docente": "OTRO DOCENTE",
    },
]


class FakeHistoryClient:
    """Cliente con historial fijo: sin red y sin curriculas."""

    base_url = BASE
    student_code = "2024000001"

    def __init__(self) -> None:
        self.history_calls = 0

    def ensure_student_code(self) -> str:
        return self.student_code

    def get_history(self) -> list[dict[str, object]]:
        self.history_calls += 1
        return [dict(row) for row in HISTORY_ROWS]
