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

BASE = "https://campus.example"
BOUNDARY = "BOUNDARY-EJEMPLO"
TASK = UploadTarget("tarea", 209901, 0, 90000001, "PISOP00001")
FOLDER = UploadTarget("carpeta", 209902, 10, 90000001, "PISOP00001")
HTML_PAGE = b"<!DOCTYPE html><html><body>Error de sesion</body></html>"


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


class _Client(CampusClient):
    """CampusClient con ``send`` guionado y contador de intentos."""

    def __init__(self, *responses: Any) -> None:
        super().__init__(base_url=BASE, delay=0)
        self._authenticated = True
        self._relogin = lambda: None  # type: ignore[method-assign]
        self.responses = list(responses)
        self.attempts = 0
        self._session.send = self.send  # type: ignore[method-assign]

    def send(self, request: Any) -> Any:
        self.attempts += 1
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, BaseException):
            raise item
        return item


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
        client = _Client(FakeResponse(b'{"d": "209901_ENTREGA.zip"}', BASE))
        seen: dict[str, Any] = {}

        def fake_open(request: Any) -> FakeResponse:
            seen["type"] = request.get_header("Content-type")
            seen["body"] = request.data
            seen["url"] = request.full_url
            return FakeResponse(b'{"d": "209901_ENTREGA.zip"}', request.full_url)

        client._session.send = fake_open  # type: ignore[method-assign]
        raw = client.upload_file(
            b"--BOUNDARY-EJEMPLO--\r\n",
            content_type=f"multipart/form-data; boundary={BOUNDARY}",
        )
        self.assertEqual(uploadform.saved_name(raw), "209901_ENTREGA.zip")
        self.assertEqual(seen["type"], f"multipart/form-data; boundary={BOUNDARY}")
        self.assertEqual(seen["body"], b"--BOUNDARY-EJEMPLO--\r\n")
        self.assertTrue(str(seen["url"]).endswith(uploadform.UPLOAD_PAGE))

    def test_un_401_reintenta_una_sola_vez(self) -> None:
        client = _Client(
            CampusHTTPError("expiro", 401),
            FakeResponse(b"209901_ENTREGA.zip", BASE),
        )
        raw = client.upload_file(b"x", content_type="multipart/form-data; boundary=B")
        self.assertEqual(raw, "209901_ENTREGA.zip")
        self.assertEqual(client.attempts, 2)

    def test_un_error_de_red_no_se_reintenta(self) -> None:
        client = _Client(CampusError("sin red"))
        with self.assertRaises(CampusError):
            client.upload_file(b"x", content_type="multipart/form-data; boundary=B")
        self.assertEqual(client.attempts, 1)

    def test_un_500_en_la_subida_no_se_reintenta(self) -> None:
        client = _Client(CampusHTTPError("500", 500))
        with self.assertRaises(CampusHTTPError):
            client.upload_file(b"x", content_type="multipart/form-data; boundary=B")
        self.assertEqual(client.attempts, 1)

    def test_una_pagina_html_no_es_un_nombre_guardado(self) -> None:
        client = _Client(FakeResponse(HTML_PAGE, BASE))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "entrega.zip"
            path.write_bytes(b"PK\x03\x04")
            plan = replace(_plan(TASK), path=path)
            with self.assertRaises(ProtocolError):
                uploader.upload(client, plan)

    def test_archivo_que_desaparece_es_error_de_uso(self) -> None:
        client = _Client(FakeResponse(b"209901_ENTREGA.zip", BASE))
        with self.assertRaises(UsageError):
            uploader.upload(client, _plan(TASK))


class InsertTests(unittest.TestCase):
    def test_un_500_en_el_registro_no_se_repite(self) -> None:
        for target, register in (
            (TASK, uploader.register_task),
            (FOLDER, uploader.register_resource),
        ):
            with self.subTest(target=target.kind):
                client = _Client(CampusHTTPError("500", 500))
                with self.assertRaises(CampusHTTPError):
                    register(client, _plan(target), "209901_ENTREGA.zip")
                self.assertEqual(client.attempts, 1)

    def test_una_lectura_normal_sigue_reintentando(self) -> None:
        client = _Client(CampusHTTPError("500", 500))
        with mock.patch("autonoma_cli.client.time.sleep"):
            with self.assertRaises(CampusHTTPError):
                client.get_courses()
        self.assertEqual(client.attempts, client.retries)


if __name__ == "__main__":
    unittest.main()
