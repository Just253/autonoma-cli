"""Destino, busqueda de la semana y cuerpo de la sincronizacion de `entregar`."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from autonoma_cli import uploader, uploadform
from autonoma_cli.errors import ProtocolError, UsageError
from autonoma_cli.models import Course, Resource, UploadPlan, UploadResult, UploadTarget

BASE = "https://campus.example"
TASK = UploadTarget("tarea", 209901, 0, 90000001, "PISOP00001")
FOLDER = UploadTarget("carpeta", 209902, 10, 90000001, "PISOP00001")


def course(**extra: Any) -> Course:
    data = {"nGruCodigo": 90000001, "asignatura": "CURSO DE EJEMPLO", "codigo": "PISOP00001"}
    data.update(extra)
    return Course.from_api(data, BASE)


def folder_resource(number: int = 209902, session: int = 10) -> Resource:
    return Resource.from_api(
        {"cTitulo": "ENTREGABLE", "nDocLinTipo": 1, "nDocLinNum": number, "nSesion": session},
        BASE,
    )


class _Sessions:
    """Cliente que solo responde la busqueda de sesiones y cuenta las lecturas."""

    def __init__(self, active: list[Resource], sessions: list[tuple[int, list[Resource]]]) -> None:
        self.active = active
        self.sessions = sessions
        self.visited: list[Any] = []

    def active_session_resources(self, group_id: object) -> list[Resource]:
        self.visited.append("activa")
        return self.active

    def iter_session_resources_lazy(self, group_id: object):
        for number, resources in self.sessions:
            self.visited.append(number)
            yield number, resources


class CodeTests(unittest.TestCase):
    def test_cdocodigo_manda_sobre_codigo(self) -> None:
        target = uploader.target_for(_Sessions([], []), course(cDocCodigo="PISOP07777"), task=209901)
        self.assertEqual(target.course_code, "PISOP07777")
        self.assertEqual(course(cDocCodigo="PISOP07777").code, "PISOP00001")

    def test_sin_cdocodigo_cae_al_codigo_del_curso(self) -> None:
        target = uploader.target_for(_Sessions([], []), course(), task=209901)
        self.assertEqual(target.course_code, "PISOP00001")


class FolderSessionTests(unittest.TestCase):
    def test_sesion_activa_evita_recorrer_el_resto(self) -> None:
        client = _Sessions([folder_resource()], [(10, [folder_resource()])])
        self.assertEqual(uploader.folder_session(client, 90000001, 209902), 10)
        self.assertEqual(client.visited, ["activa"])

    def test_recorre_sesiones_y_corta_en_la_primera(self) -> None:
        client = _Sessions(
            [],
            [(9, []), (10, [folder_resource()]), (11, [folder_resource()])],
        )
        self.assertEqual(uploader.folder_session(client, 90000001, 209902), 10)
        self.assertEqual(client.visited, ["activa", 9, 10])

    def test_carpeta_inexistente_no_inventa_la_semana(self) -> None:
        client = _Sessions([], [(9, []), (10, [])])
        with self.assertRaises(UsageError):
            uploader.folder_session(client, 90000001, 209902)
        self.assertEqual(client.visited, ["activa", 9, 10])

    def test_sesion_explicita_salta_la_busqueda(self) -> None:
        client = _Sessions([], [])
        target = uploader.target_for(
            client, course(), folder=209902, session=7
        )
        self.assertEqual(target.session, 7)
        self.assertEqual(client.visited, [])

    def test_sesion_solo_vale_con_carpeta(self) -> None:
        with self.assertRaises(UsageError):
            uploader.target_for(_Sessions([], []), course(), task=209901, session=7)


class SavedNameTests(unittest.TestCase):
    def test_una_pagina_html_no_es_un_nombre(self) -> None:
        page = "<!DOCTYPE html><html><body>Error de sesion</body></html>"
        with self.assertRaises(ProtocolError):
            uploadform.saved_name(page)

    def test_nombre_con_salto_o_ruta_se_rechaza(self) -> None:
        for value in ("209901_ENTREGA.zip\nSEGUNDA", "../../etc/passwd", "a\\b.zip"):
            with self.subTest(value=value):
                with self.assertRaises(ProtocolError):
                    uploadform.saved_name(value)

    def test_nombre_absurdamente_largo_se_rechaza(self) -> None:
        with self.assertRaises(ProtocolError):
            uploadform.saved_name("a" * (uploadform.MAX_SAVED_NAME + 1))

    def test_filename_del_multipart_escapa_comillas(self) -> None:
        body = uploadform.multipart_body(b"x", 'a"b.zip', boundary="B")
        self.assertIn(b'filename="a%22b.zip"', body)


class SyncPayloadTests(unittest.TestCase):
    def test_payload_del_campus(self) -> None:
        plan = UploadPlan(
            target=FOLDER,
            course_name="CURSO DE EJEMPLO",
            path=Path("entrega.zip"),
            title="ENTREGA DE EJEMPLO",
            description="Trabajo de ejemplo",
        )
        result = UploadResult(saved_name="209901_ENTREGA.zip", resource_id=209903)
        payload = uploadform.folder_sync_payload(
            plan, result, "2024000001", timestamp="10/11/2026 20:15:49"
        )
        self.assertEqual(
            payload,
            {
                "nDocLinNum": 209902,
                "nGruCodigo": 90000001,
                "carpetaInformation": {
                    "cDocLinUrl": "209901_ENTREGA.zip",
                    "Archivo": "209901_ENTREGA.zip",
                    "cPerCodigo": "2024000001",
                    "cDocLinComentario": "Trabajo de ejemplo",
                    "cDocLinDescripcion": "ENTREGA DE EJEMPLO",
                    "nDocLinNum": 209903,
                    "nDocLinGrupo": 209902,
                    "autor": "",
                    "fechaRegistro": "10/11/2026 20:15:49",
                },
                "silaboId": "",
                "sesionId": "",
            },
        )


if __name__ == "__main__":
    unittest.main()
