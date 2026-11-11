"""Contrato de la subida: multipart, XML, respuestas y validaciones del plan."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from autonoma_cli import uploadcheck, uploader, uploadform
from autonoma_cli.errors import CampusError, ProtocolError, UsageError
from autonoma_cli.models import Course, Resource, UploadPlan, UploadTarget

BASE = "https://campus.example"
BOUNDARY = "BOUNDARY-EJEMPLO"
TASK = UploadTarget("tarea", 209901, 0, 90000001, "PISOP00001")
FOLDER = UploadTarget("carpeta", 209902, 10, 90000001, "PISOP00001")


def course() -> Course:
    return Course.from_api(
        {
            "nGruCodigo": 90000001,
            "asignatura": "CURSO DE EJEMPLO",
            "codigo": "PISOP00001",
        },
        BASE,
    )


def folder_resource(number: int = 209902, session: int = 10) -> Resource:
    return Resource.from_api(
        {
            "cTitulo": "ENTREGABLE DE EJEMPLO",
            "nDocLinTipo": 1,
            "nDocLinNum": number,
            "nSesion": session,
            "cSesion": f"{session:02d}",
        },
        BASE,
    )


def _plan(target: UploadTarget, *, title: str = "ENTREGA", description: str = "Trabajo") -> UploadPlan:
    return UploadPlan(
        target=target,
        course_name="CURSO DE EJEMPLO",
        path=Path("entrega.zip"),
        title=title,
        description=description,
    )


class MultipartTests(unittest.TestCase):
    def test_incluye_los_campos_del_formulario(self) -> None:
        body = uploadform.multipart_body(
            b"PK\x03\x04", "entrega.zip", boundary=BOUNDARY
        )
        self.assertIn(b'name="folder0"', body)
        self.assertIn(b'name="file0"; filename="entrega.zip"', body)
        self.assertIn(b'name="path0"', body)
        self.assertIn(b"\r\n/Uploads\r\n", body)
        self.assertIn(b"PK\x03\x04", body)
        self.assertTrue(body.endswith(f"--{BOUNDARY}--\r\n".encode("utf-8")))
        self.assertNotIn(b'name="param0"', body)

    def test_param0_solo_cuando_se_pide(self) -> None:
        body = uploadform.multipart_body(
            b"datos", "entrega.zip", boundary=BOUNDARY, param0="Alumno"
        )
        self.assertIn(b'name="param0"', body)
        self.assertIn(b"\r\nAlumno\r\n", body)


class ResponseTests(unittest.TestCase):
    def test_nombre_guardado_como_texto(self) -> None:
        self.assertEqual(uploadform.saved_name("209901_ENTREGA.zip"), "209901_ENTREGA.zip")

    def test_nombre_guardado_envuelto_en_json(self) -> None:
        self.assertEqual(uploadform.saved_name('{"d": "209901_ENTREGA.zip"}'), "209901_ENTREGA.zip")

    def test_nombre_vacio_es_error_de_protocolo(self) -> None:
        with self.assertRaises(ProtocolError):
            uploadform.saved_name("   ")

    def test_rechazo_de_carpeta_trae_el_mensaje(self) -> None:
        client = _Client(resource_state=0)
        with self.assertRaises(CampusError) as raised:
            uploader.register_resource(client, _plan(FOLDER), "209901_ENTREGA.zip")
        self.assertIn("nUAEstado", str(raised.exception))
        self.assertIn("no admite mas entregas", str(raised.exception))

    def test_tarea_necesita_respuesta_mayor_que_uno(self) -> None:
        client = _Client(task_response=1)
        with self.assertRaises(CampusError):
            uploader.register_task(client, _plan(TASK), "209901_ENTREGA.zip")
        self.assertEqual(
            uploader.register_task(
                _Client(task_response=2099011), _plan(TASK), "209901_ENTREGA.zip"
            ).task_id,
            2099011,
        )


class XmlTests(unittest.TestCase):
    def test_recursos_escapa_y_manda_la_semana(self) -> None:
        plan = _plan(FOLDER, title="PRESENTACION & <ENTREGA>", description="Trabajo <final>")
        xml = uploadform.resource_xml(plan, "209901_ENTREGA.zip")
        for fragment in (
            "<url>209901_ENTREGA.zip</url>",
            "<nDocLinTipo>2</nDocLinTipo>",
            "<titulo>PRESENTACION &amp; &lt;ENTREGA&gt;</titulo>",
            "<descripcion>Trabajo &lt;final&gt;</descripcion>",
            "<Accion>A1</Accion>",
            "<nForoSesion>10</nForoSesion>",
            "<cForoPadre>0</cForoPadre>",
            "<nEstado>1</nEstado>",
            "<cDocCodigo>PISOP00001</cDocCodigo>",
            "<nSubTipoMaterial>65003210</nSubTipoMaterial>",
            "<nCarCodigo>2</nCarCodigo>",
            "<nDocLinGrupo>209902</nDocLinGrupo>",
            "<nPerRelacion>1</nPerRelacion>",
            "<encualquiermomento>0</encualquiermomento>",
        ):
            self.assertIn(fragment, xml)

    def test_tarea_lleva_los_campos_del_contrato(self) -> None:
        xml = uploadform.task_xml(_plan(TASK, title="ENTREGA & FINAL"), "209901_ENTREGA.zip")
        for fragment in (
            "<url>209901_ENTREGA.zip</url>",
            "<titulo>ENTREGA &amp; FINAL</titulo>",
            "<cDocCodigo>PISOP00001</cDocCodigo>",
            "<nDocLinNum>209901</nDocLinNum>",
            "<nGruCurso>90000001</nGruCurso>",
            "<Accion>A1</Accion>",
            "<nRespTarea>0</nRespTarea>",
            "<IDDirectory></IDDirectory>",
            "<cUuid></cUuid>",
        ):
            self.assertIn(fragment, xml)


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def _file(self, name: str = "entrega.zip", size: int = 16) -> Path:
        path = self.folder / name
        with path.open("wb") as handle:
            handle.truncate(size)
        return path

    def test_titulo_y_descripcion_son_obligatorios(self) -> None:
        path = self._file()
        for title, description in (("", "detalle"), ("titulo", "   ")):
            with self.subTest(title=title, description=description):
                with self.assertRaises(UsageError):
                    uploader.build_plan(course(), TASK, path, title, description)

    def test_archivo_inexistente_vacio_o_demasiado_grande(self) -> None:
        with self.assertRaises(UsageError):
            uploader.build_plan(course(), TASK, self.folder / "no-existe.zip", "T", "D")
        with self.assertRaises(UsageError):
            uploader.build_plan(course(), TASK, self._file(size=0), "T", "D")
        with self.assertRaises(UsageError):
            uploader.build_plan(
                course(), TASK, self._file(size=uploadcheck.MAX_BYTES + 1), "T", "D"
            )

    def test_carpeta_solo_acepta_pdf_rar_zip(self) -> None:
        with self.assertRaises(UsageError):
            uploader.build_plan(course(), FOLDER, self._file("notas.docx"), "T", "D")
        plan = uploader.build_plan(course(), FOLDER, self._file("notas.pdf"), "T", "D")
        self.assertEqual(plan.extension, "pdf")

    def test_carpeta_avisa_si_pasa_de_cinco_megas(self) -> None:
        plan = uploader.build_plan(
            course(), FOLDER, self._file(size=uploadcheck.WARN_BYTES + 1), "T", "D"
        )
        self.assertTrue(plan.warnings)
        self.assertIn("5 MB", plan.warnings[0])

    def test_param0_solo_vale_para_tareas(self) -> None:
        with self.assertRaises(UsageError):
            uploader.build_plan(course(), FOLDER, self._file(), "T", "D", param0="Alumno")
        plan = uploader.build_plan(course(), TASK, self._file(), "T", "D", param0="Alumno")
        self.assertTrue(plan.to_dict()["param0"])


class TargetTests(unittest.TestCase):
    def test_exactamente_un_destino(self) -> None:
        client = _Client()
        for folder, task in ((None, None), (209902, 209901)):
            with self.subTest(folder=folder, task=task):
                with self.assertRaises(UsageError):
                    uploader.target_for(client, course(), folder=folder, task=task)

    def test_carpeta_toma_la_semana_del_recurso(self) -> None:
        target = uploader.target_for(_Client(), course(), folder=209902)
        self.assertEqual((target.kind, target.number, target.session), ("carpeta", 209902, 10))

    def test_carpeta_inexistente_no_inventa_la_semana(self) -> None:
        with self.assertRaises(UsageError):
            uploader.target_for(_Client(folders=[]), course(), folder=209902)

    def test_curso_sin_codigo_no_puede_registrar(self) -> None:
        class NoCode:
            code = ""
            upload_code = ""
            group_id = 90000001
            name = "CURSO DE EJEMPLO"

        with self.assertRaises(UsageError):
            uploader.target_for(_Client(), NoCode(), task=209901)  # type: ignore[arg-type]


class _Client:
    """Cliente minimo: responde como el campus sin salir a la red."""

    base_url = BASE
    student_code = "2024000001"

    def __init__(
        self,
        *,
        resource_state: int = 1,
        task_response: Any = 2099011,
        folders: list[Resource] | None = None,
    ) -> None:
        self.resource_state = resource_state
        self.task_response = task_response
        self.folders = [folder_resource()] if folders is None else folders
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def active_session_resources(self, group_id: object) -> list[Resource]:
        return self.folders

    def iter_session_resources_lazy(self, group_id: object):
        yield 10, self.folders

    def ensure_student_code(self) -> str:
        return self.student_code

    def _call(
        self,
        method: str,
        payload: Any = None,
        *,
        page: str = "",
        allow_relogin: bool = True,
        retry_transient: bool = True,
    ) -> Any:
        self.calls.append((method, dict(payload or {})))
        if method == "Doc_InsertarRecurso":
            return {
                "InsertarRecursos": [
                    {
                        "nUAEstado": self.resource_state,
                        "nDocLinNum": 209903,
                        "cMensaje": "La carpeta no admite mas entregas.",
                    }
                ]
            }
        return {"d": self.task_response}


if __name__ == "__main__":
    unittest.main()
