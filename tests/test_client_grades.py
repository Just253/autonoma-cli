from __future__ import annotations

import unittest

from autonoma_cli.client import CampusClient
from autonoma_cli.errors import ProtocolError
from autonoma_cli.models import (
    AcademicSummary,
    CourseGrades,
    CycleAverage,
    GradeItem,
    HistoryCourse,
)

GRADES_PAYLOAD = {
    "fechaActualizado": "02/11/2027 20:30:30",
    "nPromTotal": "9.6",
    "porcentaje": "67",
    "notas": [
        {
            "Criterio": "EC",
            "Peso": "10",
            "nota": "20.00",
            "nSesion": 4,
            "cFechaInicio": "25/09/2027",
            "cFechaFin": "27/09/2027",
        },
        {
            "Criterio": "EP",
            "Peso": "40",
            "nota": "19.00",
            "nSesion": 8,
            "cFechaInicio": "23/10/2027",
            "cFechaFin": "25/10/2027",
        },
        {
            "Criterio": "EF",
            "Peso": "50",
            "nota": "-",
            "nSesion": 16,
            "cFechaInicio": "18/12/2027",
            "cFechaFin": "19/12/2027",
        },
    ],
}

SUMMARY_PAYLOAD = {
    "Malla_Curricular": [
        {
            "Periodo": "209901",
            "nCiclo": 1,
            "Nota": 16,
            "nNroCredito": 4,
            "nPromedioAcumulado": 15.25,
            "perMerito": 7,
        },
        {
            "Periodo": "209902",
            "nCiclo": 2,
            "Nota": 14,
            "nNroCredito": 3,
            "nPromedioAcumulado": 15.25,
            "perMerito": 7,
        },
        {
            # Sin nota: no entra en el ponderado ni en sus creditos.
            "Periodo": "209902",
            "nCiclo": 2,
            "Nota": 0,
            "nNroCredito": 5,
            "nPromedioAcumulado": 15.25,
            "perMerito": 7,
        },
    ],
    "Malla_Curricular_grafPromedioNotaByCiclo": [
        {"Periodo": "209901", "promedioPorCiclo": "15.25"},
        {"Periodo": "209902", "promedioPorCiclo": "16"},
    ],
    "Malla_Curricular_grafAvanceCarrera": [
        {"totalCreditos": "180", "totalCreditosAprobados": "40"}
    ],
}

# cTablas congelado en docs/API.md seccion 8: el test lo fija con el literal exacto.
TABLERO_TABLES_EXPECTED = (
    "Malla_Curricular,Malla_Curricular_grafPromedioNotaByCiclo,"
    "Malla_Curricular_grafAvanceCarrera,Malla_Curricular_grafTipoCurso,"
    "DatosPersonales,Competencias,PuestoAcademico"
)


class FakeGradesClient(CampusClient):
    """Cliente con respuestas sinteticas: sin red, cookies ni datos reales."""

    def __init__(self, *, grades=None, curricula=None) -> None:
        super().__init__(delay=0)
        self.calls: list[tuple[str, dict, str]] = []
        self._grades = grades if grades is not None else GRADES_PAYLOAD
        self._curricula = curricula if curricula is not None else [{"nPerAluRegCodigo": 209901}]

    def ensure_student_code(self) -> str:
        return "90000001"

    def _call(self, method, payload=None, *, page="/Campus/Default.aspx", allow_relogin=True):
        self.calls.append((method, dict(payload or {}), page))
        if method == "getNotasAlumnoGrupo":
            return self._grades
        if method == "ObtenerCurrriculasActuales":
            return self._curricula
        if method == "ObtenerDataAvanceCarrera":
            return SUMMARY_PAYLOAD
        raise AssertionError(f"metodo inesperado: {method}")


class GradesEndpointTests(unittest.TestCase):
    def test_maps_three_criteria(self) -> None:
        client = FakeGradesClient()
        grades = client.get_grades(90000001)
        self.assertEqual(client.calls[0][0], "getNotasAlumnoGrupo")
        self.assertEqual(client.calls[0][1], {"nGruCodigo": 90000001})
        self.assertEqual(grades.group_id, 90000001)
        self.assertEqual(grades.updated, "02/11/2027 20:30:30")
        self.assertEqual(grades.average, "9.6")
        self.assertEqual(grades.average_value, 9.6)
        self.assertEqual(grades.percent, 67)
        self.assertEqual([item.criterion for item in grades.items], ["EC", "EP", "EF"])

    def test_uncalled_criterion_has_no_value(self) -> None:
        grades = FakeGradesClient().get_grades(90000001)
        ef = grades.items[2]
        self.assertEqual(ef.grade, "-")
        self.assertIsNone(ef.value)
        self.assertEqual(ef.weight, 50.0)
        self.assertEqual(ef.session, 16)
        self.assertEqual(ef.start, "18/12/2027")
        self.assertEqual(grades.items[0].value, 20.0)

    def test_course_without_criteria(self) -> None:
        payload = {"fechaActualizado": "", "nPromTotal": "0", "porcentaje": "0", "notas": []}
        grades = FakeGradesClient(grades=payload).get_grades(90000001)
        self.assertEqual(grades.items, [])
        self.assertEqual(grades.average, "0")
        self.assertEqual(grades.average_value, 0.0)
        self.assertEqual(grades.percent, 0)
        self.assertEqual(grades.updated, "")

    def test_empty_fields_do_not_break(self) -> None:
        payload = {
            "fechaActualizado": None,
            "nPromTotal": "",
            "porcentaje": "",
            "notas": [{"Criterio": "EC", "Peso": "", "nota": "", "nSesion": ""}],
        }
        grades = FakeGradesClient(grades=payload).get_grades(90000001)
        self.assertEqual(grades.average, "")
        self.assertIsNone(grades.average_value)
        self.assertEqual(grades.percent, 0)
        item = grades.items[0]
        self.assertEqual(item.weight, 0.0)
        self.assertEqual(item.session, 0)
        self.assertEqual(item.grade, "")
        self.assertIsNone(item.value)

    def test_unexpected_shape_raises_protocol_error(self) -> None:
        with self.assertRaises(ProtocolError):
            FakeGradesClient(grades="texto").get_grades(90000001)


class AcademicSummaryTests(unittest.TestCase):
    def test_reads_tablero_with_two_cycles(self) -> None:
        summary = FakeGradesClient().get_academic_summary()
        self.assertIsInstance(summary, AcademicSummary)
        self.assertEqual(summary.accumulated, 15.25)
        self.assertEqual(summary.weighted, 15.14)
        self.assertEqual(summary.credits_weighted, 7.0)
        self.assertEqual(summary.credits_total, 180.0)
        self.assertEqual(summary.credits_approved, 40.0)
        self.assertEqual(summary.merit, 7)
        self.assertEqual(
            [(cycle.period, cycle.average) for cycle in summary.cycles],
            [("209901", 15.25), ("209902", 16.0)],
        )

    def test_weighted_comes_from_malla_not_official(self) -> None:
        # (16x4 + 14x3) / 7 = 15.1428... -> 15.14, distinto del oficial 15.25.
        # La fila con Nota 0 y 5 creditos no debe entrar.
        summary = AcademicSummary.from_api(SUMMARY_PAYLOAD)
        self.assertNotEqual(summary.weighted, summary.accumulated)
        self.assertEqual(summary.weighted, 15.14)
        self.assertEqual(summary.credits_weighted, 7.0)

    def test_uses_tablero_endpoint_and_frozen_tables(self) -> None:
        client = FakeGradesClient()
        client.get_academic_summary()
        methods = [method for method, _, _ in client.calls]
        self.assertEqual(
            methods, ["ObtenerCurrriculasActuales", "ObtenerDataAvanceCarrera"]
        )
        page = "/Campus/ua/Tablero/Perfil/Camp_Virt_Perfil.aspx"
        self.assertEqual(client.calls[0][1], {"cPerCodigo": "90000001"})
        self.assertEqual(client.calls[0][2], page)
        payload = client.calls[1][1]
        self.assertEqual(payload["cPerCodigo"], "")
        self.assertEqual(payload["nPerAluRegCodigo"], 209901)
        self.assertEqual(payload["cTablas"], TABLERO_TABLES_EXPECTED)
        self.assertEqual(client.calls[1][2], page)

    def test_without_enrollment_raises(self) -> None:
        client = FakeGradesClient(curricula=[])
        with self.assertRaises(ProtocolError):
            client.get_academic_summary()

    def test_without_official_average_raises(self) -> None:
        rows = [
            {key: value for key, value in row.items() if key != "nPromedioAcumulado"}
            for row in SUMMARY_PAYLOAD["Malla_Curricular"]
        ]
        payload = {**SUMMARY_PAYLOAD, "Malla_Curricular": rows}
        with self.assertRaises(ProtocolError):
            AcademicSummary.from_api(payload)


class GradesDictTests(unittest.TestCase):
    """Claves exactas del JSON: cambiarlas rompe docs/JSON.md y los comandos."""

    def test_grade_item_keys(self) -> None:
        payload = GradeItem.from_api(GRADES_PAYLOAD["notas"][0]).to_dict()
        self.assertEqual(
            set(payload),
            {"criterion", "weight", "grade", "grade_value", "session", "from", "to"},
        )
        self.assertEqual(payload["grade_value"], 20.0)
        self.assertEqual(payload["from"], "25/09/2027")

    def test_course_grades_keys(self) -> None:
        payload = CourseGrades.from_api(GRADES_PAYLOAD, group_id=90000001).to_dict()
        self.assertEqual(
            set(payload),
            {"group_id", "updated", "average", "average_value", "percent", "items"},
        )
        self.assertEqual(set(payload["items"][0]), set(GradeItem.from_api({}).to_dict()))
        self.assertEqual(payload["group_id"], 90000001)

    def test_academic_summary_keys(self) -> None:
        payload = AcademicSummary.from_api(SUMMARY_PAYLOAD).to_dict()
        self.assertEqual(
            list(payload),
            [
                "accumulated",
                "weighted",
                "credits_weighted",
                "credits_total",
                "credits_approved",
                "merit",
                "cycles",
            ],
        )
        self.assertEqual(payload["weighted"], 15.14)
        self.assertEqual(payload["credits_weighted"], 7.0)
        self.assertEqual(payload["cycles"][0], {"period": "209901", "average": 15.25})
        self.assertEqual(set(CycleAverage("209901", 15.25).to_dict()), {"period", "average"})

    def test_history_course_grade(self) -> None:
        course = HistoryCourse.from_api({"nGruCodigo": 90000001, "nPromocional": "18"})
        self.assertEqual(course.grade, "18")
        self.assertEqual(course.grade_value, 18.0)
        self.assertEqual(course.to_dict()["grade"], "18")

    def test_history_course_without_grade(self) -> None:
        course = HistoryCourse.from_api({"nGruCodigo": 90000001})
        self.assertEqual(course.grade, "")
        self.assertIsNone(course.grade_value)
        self.assertEqual(course.to_dict()["grade"], "")


if __name__ == "__main__":
    unittest.main()
