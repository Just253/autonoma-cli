"""Subida y registro con la red simulada: que se reintenta y que no."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest import mock

from autonoma_cli import uploader, uploadform
from autonoma_cli.client import CampusClient
from autonoma_cli.errors import CampusError, CampusHTTPError, ProtocolError, UsageError
from autonoma_cli.models import UploadPlan, UploadTarget
from support.session import FakeSession, save_cookie

BASE = "https://campus.example"
HOME_URL = f"{BASE}/Campus/Default.aspx"
BOUNDARY = "BOUNDARY-EJEMPLO"
TASK = UploadTarget("tarea", 209901, 0, 90000001, "PISOP00001")
FOLDER = UploadTarget("carpeta", 209902, 10, 90000001, "PISOP00001")
HTML_PAGE = b"<!DOCTYPE html><html><body>Error de sesion</body></html>"
LOGIN_HTML = '<form name="frmLogin" method="post" action="./Login.aspx"></form>'
HOME_HTML = '<html><body><input id="cPerCodigo" value="9000000001" /></body></html>'


class FakeResponse:
    def __init__(self, body: bytes, url: str) -> None:
        self.body = body
        self.url = url

    def geturl(self) -> str:
        return self.url

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _client(*responses: Any, retries: int = 3) -> tuple[CampusClient, FakeSession]:
    """Cliente autenticado por la cookie guardada, con la sesion guionada."""

    session = FakeSession(*responses)
    save_cookie(session)
    client = CampusClient(base_url=BASE, delay=0, retries=retries, session=session)
    client.authenticate("90000001", "clave-de-ejemplo")
    return client, session


def _plan(target: UploadTarget) -> UploadPlan:
    return UploadPlan(
        target=target,
        course_name="CURSO DE EJEMPLO",
        path=Path("entrega.zip"),
        title="ENTREGA",
        description="Trabajo",
    )


class UploadFileTests(unittest.TestCase):
    def test_manda_el_cuerpo_y_lee_el_nombre(self) -> None:
        client, session = _client(FakeResponse(b'{"d": "209901_ENTREGA.zip"}', BASE))

        raw = client.upload_file(
            b"--BOUNDARY-EJEMPLO--\r\n",
            content_type=f"multipart/form-data; boundary={BOUNDARY}",
        )

        request = session.requests[-1]
        self.assertEqual(uploadform.saved_name(raw), "209901_ENTREGA.zip")
        self.assertEqual(
            request.get_header("Content-type"),
            f"multipart/form-data; boundary={BOUNDARY}",
        )
        self.assertEqual(request.data, b"--BOUNDARY-EJEMPLO--\r\n")
        self.assertTrue(str(request.full_url).endswith(uploadform.UPLOAD_PAGE))

    def test_un_401_reintenta_una_sola_vez(self) -> None:
        client, session = _client(
            CampusHTTPError("expiro", 401),
            FakeResponse(b"", BASE),
            FakeResponse(HOME_HTML.encode("utf-8"), HOME_URL),
            FakeResponse(b"209901_ENTREGA.zip", BASE),
        )

        raw = client.upload_file(b"x", content_type="multipart/form-data; boundary=B")

        self.assertEqual(raw, "209901_ENTREGA.zip")
        uploads = [
            request for request in session.requests
            if str(request.full_url).endswith(uploadform.UPLOAD_PAGE)
        ]
        self.assertEqual(len(uploads), 2)

    def test_un_error_de_red_no_se_reintenta(self) -> None:
        client, session = _client(CampusError("sin red"))
        with self.assertRaises(CampusError):
            client.upload_file(b"x", content_type="multipart/form-data; boundary=B")
        self.assertEqual(session.attempts, 1)

    def test_un_500_en_la_subida_no_se_reintenta(self) -> None:
        client, session = _client(CampusHTTPError("500", 500))
        with self.assertRaises(CampusHTTPError):
            client.upload_file(b"x", content_type="multipart/form-data; boundary=B")
        self.assertEqual(session.attempts, 1)

    def test_una_pagina_html_no_es_un_nombre_guardado(self) -> None:
        client, _ = _client(FakeResponse(HTML_PAGE, BASE))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entrega.zip"
            path.write_bytes(b"PK\x03\x04")
            plan = replace(_plan(TASK), path=path)
            with self.assertRaises(ProtocolError):
                uploader.upload(client, plan)

    def test_archivo_que_desaparece_es_error_de_uso(self) -> None:
        client, _ = _client(FakeResponse(b"209901_ENTREGA.zip", BASE))
        with self.assertRaises(UsageError):
            uploader.upload(client, _plan(TASK))


class InsertTests(unittest.TestCase):
    def test_un_500_en_el_registro_no_se_repite(self) -> None:
        for target, register in (
            (TASK, uploader.register_task),
            (FOLDER, uploader.register_resource),
        ):
            with self.subTest(target=target.kind):
                client, session = _client(CampusHTTPError("500", 500))
                with self.assertRaises(CampusHTTPError):
                    register(client, _plan(target), "209901_ENTREGA.zip")
                self.assertEqual(session.attempts, 1)

    def test_una_lectura_normal_sigue_reintentando(self) -> None:
        client, session = _client(CampusHTTPError("500", 500))
        with mock.patch("autonoma_cli.api.call.time.sleep"):
            with self.assertRaises(CampusHTTPError):
                client.get_courses()
        self.assertEqual(session.attempts, client.retries)


if __name__ == "__main__":
    unittest.main()
