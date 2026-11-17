from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request

from autonoma_cli.errors import CampusError, CampusHTTPError, SessionExpiredError
from autonoma_cli.files import (
    Manifest,
    build_filename,
    course_folder,
    download_file,
    plan_course,
)
from autonoma_cli.models import Course, Resource
from autonoma_cli.ui import human_size

BASE = "https://virtual.autonoma.edu.pe"
HEADERS = {"User-Agent": "autonoma-cli/0 (+uso-personal)", "Accept-Language": "es-PE"}


def make_course(group: int = 1, name: str = "CURSO DE EJEMPLO UNO") -> Course:
    return Course.from_api({"nGruCodigo": group, "asignatura": name}, BASE)


def make_resource(title: str, kind: int = 2, session: int = 1, url: str = "a.pdf") -> Resource:
    return Resource.from_api(
        {
            "cTitulo": title,
            "nDocLinTipo": kind,
            "nDocLinNum": 1,
            "nSesion": session,
            "url": url,
        },
        BASE,
        session=session,
    )


class FakeResponse:
    """Respuesta minima: ``read`` por bloques y contexto, como la del opener."""

    def __init__(self, body: bytes, url: str = "") -> None:
        self.body = body
        self.url = url

    def geturl(self) -> str:
        return self.url

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body)
        chunk, self.body = self.body[:size], self.body[size:]
        return chunk

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


class FakeSend:
    """Transporte falso: respuestas guionadas y los pedidos que recibio."""

    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.requests: list[Request] = []
        self.cookies: list[bool] = []

    def __call__(self, request: Request, *, cookies: bool = True) -> FakeResponse:
        self.requests.append(request)
        self.cookies.append(cookies)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, BaseException):
            raise item
        return item


class FilenameTests(unittest.TestCase):
    def test_course_folder_is_slug(self) -> None:
        self.assertEqual(course_folder(make_course()), "CURSO_DE_EJEMPLO_UNO")

    def test_build_filename_contains_kind_and_extension(self) -> None:
        name = build_filename(make_resource("PRESENTACIÓN: TEMA"))
        self.assertTrue(name.startswith("ARCHIVO_"))
        self.assertTrue(name.endswith(".pdf"))
        self.assertNotIn(":", name)

    def test_human_size(self) -> None:
        self.assertEqual(human_size(512), "512 B")
        self.assertEqual(human_size(2048), "2.0 KB")
        self.assertEqual(human_size(5 * 1024 * 1024), "5.0 MB")


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.course = make_course()
        self.sessions = [
            (1, [make_resource("PRESENTACION: A", url="a.pdf"), make_resource("TAREA: B", kind=4, url="b.pdf")]),
            (2, [make_resource("LECTURA: C", session=2, url="c.pdf"), make_resource("CARPETA", kind=1, session=2)]),
        ]

    def test_plan_structure(self) -> None:
        items = plan_course(self.course, self.sessions, self.root)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].path, self.root / "CURSO_DE_EJEMPLO_UNO" / "Sesion_01" / "ARCHIVO_PRESENTACION_A.pdf")
        self.assertEqual(items[1].resource.kind_name, "Tarea")
        self.assertEqual(items[2].path.parent.name, "Sesion_02")

    def test_kind_filter(self) -> None:
        items = plan_course(self.course, self.sessions, self.root, kinds={4})
        self.assertEqual([item.resource.title for item in items], ["TAREA: B"])

    def test_regex_filter(self) -> None:
        items = plan_course(self.course, self.sessions, self.root, only=re.compile("lectura", re.I))
        self.assertEqual([item.resource.title for item in items], ["LECTURA: C"])

    def test_folder_resources_are_skipped(self) -> None:
        items = plan_course(self.course, self.sessions, self.root)
        self.assertNotIn("CARPETA", [item.resource.title for item in items])

    def test_duplicate_titles_get_suffix(self) -> None:
        sessions = [(1, [make_resource("MISMO", url="a.pdf"), make_resource("MISMO", url="b.pdf")])]
        items = plan_course(self.course, sessions, self.root)
        self.assertEqual(len({item.path for item in items}), 2)
        self.assertTrue(any("(2)" in item.path.name for item in items))


class ManifestTests(unittest.TestCase):
    def test_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = Manifest(root)
            manifest.put("https://x/a.pdf", {"bytes": 10, "sha256": "abc"})
            manifest.save()

            document = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("https://x/a.pdf", document["entries"])

            again = Manifest(root)
            self.assertEqual(again.get("https://x/a.pdf")["bytes"], 10)
            self.assertIsNone(again.get("https://x/nada.pdf"))


class DownloadFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "curso" / "a.pdf"
        self.partial = self.target.with_name("a.pdf.part")

    def test_writes_file_and_returns_size_and_sha(self) -> None:
        body = b"%PDF-1.4 datos"
        send = FakeSend(FakeResponse(body))
        size, sha = download_file(send, "https://x/a.pdf", self.target, headers=HEADERS)
        self.assertEqual(size, len(body))
        self.assertEqual(sha, hashlib.sha256(body).hexdigest())
        self.assertEqual(self.target.read_bytes(), body)
        self.assertFalse(self.partial.exists())

    def test_request_uses_the_session_headers_and_no_cookie(self) -> None:
        send = FakeSend(FakeResponse(b"x"))
        download_file(
            send,
            "https://x/a.pdf",
            self.target,
            headers=HEADERS,
            referer="https://x/Campus/Default.aspx",
        )
        request = send.requests[0]
        self.assertEqual(request.get_header("User-agent"), HEADERS["User-Agent"])
        self.assertEqual(request.get_header("Accept"), "*/*")
        self.assertEqual(request.get_header("Referer"), "https://x/Campus/Default.aspx")
        self.assertFalse([key for key in request.headers if key.lower() == "cookie"])
        self.assertEqual(send.cookies, [False], "el archivo es publico: sin cookie")

    def test_empty_body_is_an_error_and_retries(self) -> None:
        send = FakeSend(FakeResponse(b""))
        with mock.patch("autonoma_cli.files.fetch.time.sleep"):
            with self.assertRaises(CampusError) as context:
                download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=2)
        self.assertIn("vacio", str(context.exception))
        self.assertEqual(len(send.requests), 2)
        self.assertFalse(self.partial.exists())

    def test_client_error_is_not_retried(self) -> None:
        send = FakeSend(CampusHTTPError("El campus respondio HTTP 404.", 404))
        with self.assertRaises(CampusError) as context:
            download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=3)
        self.assertIn("No se pudo descargar https://x/a.pdf", str(context.exception))
        self.assertEqual(len(send.requests), 1)
        self.assertFalse(self.target.exists())

    def test_server_error_is_retried(self) -> None:
        send = FakeSend(CampusHTTPError("El campus respondio HTTP 503.", 503), FakeResponse(b"ok"))
        with mock.patch("autonoma_cli.files.fetch.time.sleep"):
            size, _ = download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=3)
        self.assertEqual(size, 2)
        self.assertEqual(len(send.requests), 2)

    def test_request_timeout_is_retried(self) -> None:
        send = FakeSend(CampusHTTPError("El campus respondio HTTP 408.", 408), FakeResponse(b"ok"))
        with mock.patch("autonoma_cli.files.fetch.time.sleep"):
            size, _ = download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=3)
        self.assertEqual(size, 2)
        self.assertEqual(len(send.requests), 2)

    def test_too_many_requests_is_retried(self) -> None:
        send = FakeSend(CampusHTTPError("El campus respondio HTTP 429.", 429), FakeResponse(b"ok"))
        with mock.patch("autonoma_cli.files.fetch.time.sleep"):
            size, _ = download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=3)
        self.assertEqual(size, 2)
        self.assertEqual(len(send.requests), 2)

    def test_network_error_is_retried(self) -> None:
        send = FakeSend(CampusError("No se pudo conectar con el campus."), FakeResponse(b"ok"))
        with mock.patch("autonoma_cli.files.fetch.time.sleep"):
            size, _ = download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=3)
        self.assertEqual(size, 2)
        self.assertEqual(len(send.requests), 2)

    def test_login_redirect_is_not_saved(self) -> None:
        login = FakeResponse(b"<html>login</html>", url="https://x/Campus/Login.aspx?ReturnUrl=1")
        send = FakeSend(login)
        with self.assertRaises(SessionExpiredError):
            download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=3)
        self.assertEqual(len(send.requests), 2)
        self.assertEqual(send.cookies, [False, True], "reintenta una vez con la sesion")
        self.assertFalse(self.target.exists())
        self.assertFalse(self.partial.exists())

    def test_un_401_sin_cookie_reintenta_con_la_sesion(self) -> None:
        send = FakeSend(CampusHTTPError("El campus respondio HTTP 401.", 401), FakeResponse(b"ok"))
        size, _ = download_file(send, "https://x/a.pdf", self.target, headers=HEADERS)
        self.assertEqual(size, 2)
        self.assertEqual(send.cookies, [False, True])

    def test_un_401_con_cookie_es_sesion_vencida(self) -> None:
        send = FakeSend(CampusHTTPError("El campus respondio HTTP 401.", 401))
        with self.assertRaises(SessionExpiredError):
            download_file(send, "https://x/a.pdf", self.target, headers=HEADERS, retries=3)
        self.assertEqual(send.cookies, [False, True])
        self.assertFalse(self.target.exists())
        self.assertFalse(self.partial.exists())

    def test_la_ruta_protegida_se_reintenta_con_la_sesion(self) -> None:
        login = FakeResponse(b"<html>login</html>", url="https://x/Campus/Login.aspx")
        body = b"%PDF-1.4 datos"
        send = FakeSend(login, FakeResponse(body, url="https://x/a.pdf"))
        size, _ = download_file(send, "https://x/a.pdf", self.target, headers=HEADERS)
        self.assertEqual(size, len(body))
        self.assertEqual(send.cookies, [False, True])
        self.assertEqual(self.target.read_bytes(), body)


if __name__ == "__main__":
    unittest.main()
