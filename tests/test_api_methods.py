"""WebMethods: rutas, payloads y mapeo a los modelos, sin red."""

from __future__ import annotations

import unittest
from unittest import mock

from autonoma_cli.api import ApiContext, methods, resources
from autonoma_cli.errors import ProtocolError
from support.session import FakeSession

BASE = "https://campus-de-ejemplo.edu"
DEFAULT_PAGE = "/Campus/Default.aspx"
TABLERO_PAGE = "/Campus/ua/Tablero/Perfil/Camp_Virt_Perfil.aspx"
CURRICULA_PAGE = "/Modulos/Campus/MisCursos/Ca_Mc_CursosMatriculados.aspx"
HISTORY_PAGE = "/CampusVirtual/ua/Alumno/MisCursos/Alu_HistorialCursos.aspx"
TABLERO_TABLES = (
    "Malla_Curricular,Malla_Curricular_grafPromedioNotaByCiclo,"
    "Malla_Curricular_grafAvanceCarrera,Malla_Curricular_grafTipoCurso,"
    "DatosPersonales,Competencias,PuestoAcademico"
)


class FakeAuth:
    def __init__(self, code: str = "90000001") -> None:
        self.code = code

    def ensure_student_code(self) -> str:
        return self.code


def _ctx(code: str = "90000001") -> ApiContext:
    return ApiContext(BASE, {}, FakeSession(), FakeAuth(code), 3)


def course(group_id: int = 90000001) -> dict:
    return {
        "nGruCodigo": group_id,
        "asignatura": "CURSO DE EJEMPLO",
        "codigo": "PISOP00001",
    }


def resource(session: int, kind: int = 2, url: str = "a.pdf") -> dict:
    return {
        "cTitulo": "MATERIAL DE EJEMPLO",
        "nDocLinTipo": kind,
        "nDocLinNum": session,
        "nSesion": session,
        "cSesion": f"{session:02d}",
        "url": url,
    }


SUMMARY = {
    "Malla_Curricular": [
        {"Periodo": "209901", "nCiclo": 1, "Nota": 16, "nNroCredito": 4,
         "nPromedioAcumulado": 15.25, "perMerito": 7}
    ],
    "Malla_Curricular_grafPromedioNotaByCiclo": [
        {"Periodo": "209901", "promedioPorCiclo": "15.25"}
    ],
    "Malla_Curricular_grafAvanceCarrera": [
        {"totalCreditos": "180", "totalCreditosAprobados": "40"}
    ],
}


class FakeCalls(unittest.TestCase):
    """Reemplaza ``api.methods.call`` por respuestas guionadas."""

    def run_calls(self, responses, function, *args, **kwargs):
        calls: list[tuple[str, dict, str]] = []

        def fake(ctx, method, payload=None, *, page=DEFAULT_PAGE, **rest):
            calls.append((method, dict(payload or {}), page))
            if callable(responses):
                return responses(method, payload or {})
            return responses[method]

        with mock.patch("autonoma_cli.api.methods.call", fake):
            result = function(*args, **kwargs)
        return result, calls


class CourseTests(FakeCalls):
    def test_get_courses_descarta_filas_sin_codigo(self) -> None:
        payload = [course(), {"asignatura": "SIN CODIGO"}, "texto"]
        result, calls = self.run_calls(
            {"Alu_ObtenerCursosActuales": payload}, methods.get_courses, _ctx()
        )
        self.assertEqual([item.group_id for item in result], [90000001])
        self.assertEqual(calls, [("Alu_ObtenerCursosActuales", {}, DEFAULT_PAGE)])

    def test_get_courses_sin_lista_es_error_de_protocolo(self) -> None:
        with self.assertRaises(ProtocolError):
            self.run_calls(
                {"Alu_ObtenerCursosActuales": {"nGruCodigo": 1}},
                methods.get_courses,
                _ctx(),
            )

    def test_get_course_detail_manda_perfil_y_sesion(self) -> None:
        _, calls = self.run_calls(
            {"getInformationDetailCurso": {}},
            methods.get_course_detail,
            _ctx(),
            90000001,
            2,
        )
        self.assertEqual(
            calls[0],
            (
                "getInformationDetailCurso",
                {"nGruCodigo": 90000001, "nSesion": 2, "nPerfil": 13},
                DEFAULT_PAGE,
            ),
        )

    def test_get_curricula_usa_el_codigo_y_su_pagina(self) -> None:
        result, calls = self.run_calls(
            {"obtenerUniOrgCurriculo": {"recursos": [{"nCurCodigo": 1}]}},
            methods.get_curricula,
            _ctx("90000001"),
        )
        self.assertEqual(result, [{"nCurCodigo": 1}])
        self.assertEqual(
            calls[0],
            (
                "obtenerUniOrgCurriculo",
                {"cPerCodigo": "90000001", "nTipCur": 1},
                CURRICULA_PAGE,
            ),
        )

    def test_get_history_recorre_curriculas_y_deduplica(self) -> None:
        def responses(method, payload):
            if method == "obtenerUniOrgCurriculo":
                return [{"nCurCodigo": 1}, {"nCurCodigo": 2}]
            if payload.get("nCurCodigo") == 1:
                return {"HISTORIAL_CURSOS": [{"nGruCodigo": 11}, {"nGruCodigo": 12}]}
            return {"HISTORIAL_CURSOS": [{"nGruCodigo": 12}, {"nGruCodigo": 13}]}

        rows, calls = self.run_calls(responses, methods.get_history, _ctx())
        self.assertEqual([row["nGruCodigo"] for row in rows], [11, 12, 13])
        self.assertEqual(
            [page for _, _, page in calls], [CURRICULA_PAGE, HISTORY_PAGE, HISTORY_PAGE]
        )

    def test_get_syllabus_mapea_solo_los_mappings(self) -> None:
        topics, _ = self.run_calls(
            {"getInformationDetailCurso": {"silabo": [{"nSesion": 1, "tema": "Tema"}, "x"]}},
            methods.get_syllabus,
            _ctx(),
            90000001,
        )
        self.assertEqual([topic.number for topic in topics], [1])

    def test_get_schedule_mapea_la_programacion(self) -> None:
        sessions, _ = self.run_calls(
            {
                "getProgramacionAlumnoGrupo": [
                    {"nSesion": 3, "tema": "Clase", "fecha": "01/03/2027 08:00 a 10:00"}
                ]
            },
            methods.get_schedule,
            _ctx(),
            90000001,
            course="CURSO DE EJEMPLO",
        )
        self.assertEqual((sessions[0].number, sessions[0].course), (3, "CURSO DE EJEMPLO"))
        self.assertEqual(sessions[0].time_range, "08:00-10:00")


class GradeTests(FakeCalls):
    def test_get_grades_sin_mapping_es_error_de_protocolo(self) -> None:
        with self.assertRaises(ProtocolError):
            self.run_calls(
                {"getNotasAlumnoGrupo": "texto"}, methods.get_grades, _ctx(), 90000001
            )

    def test_get_grades_mapea_los_criterios(self) -> None:
        payload = {
            "fechaActualizado": "",
            "nPromTotal": "0",
            "porcentaje": "0",
            "notas": [{"Criterio": "EC", "Peso": "10", "nota": "20.00", "nSesion": 1}],
        }
        grades, calls = self.run_calls(
            {"getNotasAlumnoGrupo": payload}, methods.get_grades, _ctx(), 90000001
        )
        self.assertEqual((grades.group_id, grades.items[0].criterion), (90000001, "EC"))
        self.assertEqual(calls[0][1], {"nGruCodigo": 90000001})

    def test_get_academic_summary_ordena_y_congela_tablas(self) -> None:
        def responses(method, payload):
            if method == "ObtenerCurrriculasActuales":
                return [{"nPerAluRegCodigo": 209901}]
            return SUMMARY

        summary, calls = self.run_calls(responses, methods.get_academic_summary, _ctx())
        self.assertEqual(summary.accumulated, 15.25)
        self.assertEqual(
            [method for method, _, _ in calls],
            ["ObtenerCurrriculasActuales", "ObtenerDataAvanceCarrera"],
        )
        self.assertEqual(calls[0][1], {"cPerCodigo": "90000001"})
        self.assertEqual(calls[0][2], TABLERO_PAGE)
        self.assertEqual(
            calls[1][1],
            {"cPerCodigo": "", "nPerAluRegCodigo": 209901, "cTablas": TABLERO_TABLES},
        )

    def test_get_academic_summary_sin_matricula_es_error_de_protocolo(self) -> None:
        with self.assertRaises(ProtocolError):
            self.run_calls(
                {"ObtenerCurrriculasActuales": []}, methods.get_academic_summary, _ctx()
            )


class ResourceTests(FakeCalls):
    def test_get_session_resources_resuelve_la_url(self) -> None:
        resources_, calls = self.run_calls(
            {"getInformationDetailCurso": [resource(1)]},
            resources.get_session_resources,
            _ctx(),
            90000001,
            1,
        )
        self.assertEqual(resources_[0].url, f"{BASE}/uploads/a.pdf")
        self.assertEqual(calls[0][1]["nSesion"], 1)

    def test_la_sesion_activa_es_la_cero(self) -> None:
        _, calls = self.run_calls(
            {"getInformationDetailCurso": [resource(0)]},
            resources.active_session_resources,
            _ctx(),
            90000001,
        )
        self.assertEqual(calls[0][1]["nSesion"], 0)

    def test_iter_recorre_el_silabo_y_filtra_carpetas(self) -> None:
        def responses(method, payload):
            session = payload.get("nSesion")
            if session == 0:
                return {"silabo": [{"nSesion": 1}, {"nSesion": 2}]}
            if session == 1:
                return [resource(1, 2), resource(1, 0)]
            return [resource(2, 4)]

        pairs, _ = self.run_calls(
            responses, resources.iter_session_resources, _ctx(), 90000001, max_sessions=5
        )
        self.assertEqual(
            [(number, [item.kind for item in items]) for number, items in pairs],
            [(1, [2]), (2, [4])],
        )

    def test_iter_usa_las_sesiones_pedidas_sin_leer_el_silabo(self) -> None:
        pairs, calls = self.run_calls(
            {"getInformationDetailCurso": [resource(5)]},
            resources.iter_session_resources,
            _ctx(),
            90000001,
            [5],
            max_sessions=5,
        )
        self.assertEqual([number for number, _ in pairs], [5])
        self.assertEqual([payload["nSesion"] for _, payload, _ in calls], [5])

    def test_iter_sin_silabo_prueba_max_sessions_y_corta(self) -> None:
        pairs, calls = self.run_calls(
            {"getInformationDetailCurso": []},
            resources.iter_session_resources,
            _ctx(),
            90000001,
            max_sessions=5,
        )
        self.assertEqual([number for number, _ in pairs], [1, 2])
        self.assertEqual(len(calls), 3)

    def test_iter_lazy_no_pide_lo_que_no_se_consume(self) -> None:
        calls: list[str] = []

        def responses(method, payload):
            calls.append(method)
            return [resource(payload["nSesion"])]

        def first(ctx):
            return next(resources.iter_session_resources_lazy(ctx, 90000001, [1, 2, 3], max_sessions=5))

        pair, _ = self.run_calls(responses, first, _ctx())
        self.assertEqual(pair[0], 1)
        self.assertEqual(calls, ["getInformationDetailCurso"])


if __name__ == "__main__":
    unittest.main()
