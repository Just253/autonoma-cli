from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from autonoma_cli.client import CampusClient
from autonoma_cli.downloader import Manifest, plan_course, run_plan
from autonoma_cli.errors import AuthenticationError

LOGIN_PAGE = """<!doctype html><html><body>
<form name="frmLogin" method="post" action="./Login.aspx" id="frmLogin">
  <input type="hidden" name="__VIEWSTATE" value="VIEWSTATE" />
  <input type="hidden" name="__EVENTVALIDATION" value="EVENTVALIDATION" />
  <input name="txtUsuario" id="txtUsuario" type="text" name="email-username" />
  <input name="txtPassword" id="txtPassword" type="password" name="password" />
  <input type="submit" name="btn_ingresar" value="Ingresar" id="btn_ingresar" />
</form>
<span id="FailureText">Usuario y/o password incorrecto.</span>
</body></html>"""

HOME_PAGE = """<!doctype html><html><body>
<input id="cPerCodigo" value="9000000001" />
</body></html>"""

COURSE = {
    "nGruCodigo": 90000001,
    "asignatura": "CURSO DE EJEMPLO",
    "codigo": "PISOP00001",
    "periodo": "209901",
    "ciclo": 1,
    "seccion": "1",
    "grupo": "1A1-A",
    "creditos": 4,
    "modalidad": "VIRTUAL",
    "docenteNombre": "DOCENTE",
    "docenteApellido": "DE EJEMPLO",
    "fechaInicioCurso": "01/03/2027",
    "fechaFinCurso": "30/06/2027",
    "cantidadRecursos": 12,
    "EstadoCurso": 1,
}

SILABO = [
    {
        "nSesion": 1,
        "cSesion": "01",
        "semana_fecha_inicio": "01/03/2027",
        "semana_fecha_fin": "07/03/2027",
        "tema": "Tema de ejemplo uno\nValor: compromiso",
        "logro": "Analiza el tema de ejemplo",
        "sesion_activa": 1,
    },
    {
        "nSesion": 2,
        "cSesion": "02",
        "semana_fecha_inicio": "08/03/2027",
        "semana_fecha_fin": "14/03/2027",
        "tema": "Tema de ejemplo dos",
        "logro": "Redacta una propuesta",
        "sesion_activa": 0,
    },
]

PDF_BYTES = b"%PDF-1.4\n% fake\n1 0 obj\n<<>>\nendobj\n"


def resource(session: int, title: str, url: str, kind: int = 2) -> dict:
    return {
        "cTitulo": title,
        "nDocLinTipo": kind,
        "nDocLinNum": session,
        "nSesion": session,
        "cSesion": f"{session:02d}",
        "url": url,
        "clase": "far fa-file-pdf" if kind == 2 else "ti ti-list-check",
        "dDocTraFec": "01/03/2027",
        "nItinerario": 2,
    }


class FakeCampus(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # silencia el log del servidor
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/html; charset=utf-8", extra=None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - API de BaseHTTPRequestHandler
        path = self.path.split("?")[0]
        if path == "/Campus/Login.aspx":
            self._send(200, LOGIN_PAGE.encode("utf-8"))
        elif path == "/Campus/Default.aspx":
            self._send(200, HOME_PAGE.encode("utf-8"))
        elif path.startswith("/uploads/"):
            self._send(200, PDF_BYTES, "application/pdf")
        else:
            self._send(404, b"not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)

        if path == "/Campus/Login.aspx":
            form = parse_qs(raw.decode("utf-8"))
            ok = form.get("txtUsuario") == ["alumno"] and form.get("txtPassword") == ["clave"]
            if ok:
                self._send(
                    302,
                    b"",
                    extra={
                        "Location": "/Campus/Default.aspx",
                        "Set-Cookie": "ASP.NET_SessionId=abc123; Path=/",
                    },
                )
            else:
                self._send(200, LOGIN_PAGE.encode("utf-8"))
            return

        payload = json.loads(raw.decode("utf-8")) if raw else {}

        if path.endswith("/Alu_ObtenerCursosActuales"):
            self._send(200, json.dumps({"d": [COURSE]}).encode("utf-8"), "application/json")
            return

        if path.endswith("/getInformationDetailCurso"):
            session = int(payload.get("nSesion", 0))
            if session == 0:
                data = {
                    "silabo": SILABO,
                    "recursos": [resource(1, "PRESENTACION: A", "a.pdf")],
                    "rutaAprendizaje": [],
                }
            elif session == 1:
                data = [
                    resource(1, "PRESENTACION: A", "a.pdf"),
                    resource(1, "TAREA: B", "b.pdf", kind=4),
                    resource(1, "CARPETA", "", kind=1),
                ]
            else:
                data = []
            self._send(200, json.dumps({"d": json.dumps(data)}).encode("utf-8"), "application/json")
            return

        self._send(404, b"not found")


class FakeCampusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = HTTPServer(("127.0.0.1", 0), FakeCampus)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.client = CampusClient(
            base_url=self.base,
            delay=0,
            cookies_file=str(self.folder / "session.cookies"),
        )

    def _login(self) -> None:
        self.client.login("alumno", "clave")

    def test_login_and_student_code(self) -> None:
        self._login()
        self.assertTrue(self.client.authenticated)
        self.assertEqual(self.client.student_code, "9000000001")
        self.assertTrue((self.folder / "session.cookies").exists())

    def test_bad_password_raises_with_campus_message(self) -> None:
        with self.assertRaises(AuthenticationError) as context:
            self.client.login("alumno", "otra")
        self.assertIn("incorrecto", str(context.exception))

    def test_courses_and_syllabus(self) -> None:
        self._login()
        courses = self.client.get_courses()
        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0].name, "CURSO DE EJEMPLO")
        topics = self.client.get_syllabus(courses[0].group_id)
        self.assertEqual([topic.number for topic in topics], [1, 2])
        self.assertTrue(topics[0].active)

    def test_session_resources(self) -> None:
        self._login()
        resources = self.client.get_session_resources(90000001, 1)
        self.assertEqual(len(resources), 3)
        self.assertEqual(resources[0].url, f"{self.base}/uploads/a.pdf")
        self.assertFalse(resources[2].downloadable)

    def test_download_and_manifest_skip(self) -> None:
        self._login()
        courses = self.client.get_courses()
        course = courses[0]
        sessions = [(1, self.client.get_session_resources(course.group_id, 1))]
        items = plan_course(course, sessions, self.folder)
        self.assertEqual([item.resource.kind_name for item in items], ["Archivo", "Tarea"])

        manifest = Manifest(self.folder)
        stats = run_plan(items, manifest, cookie_header=self.client.cookie_header(), workers=1)
        self.assertEqual(stats.downloaded, 2)
        self.assertEqual(stats.failed, 0)
        target = items[0].path
        self.assertEqual(target.read_bytes()[:5], b"%PDF-")

        manifest = Manifest(self.folder)
        again = run_plan(items, manifest, cookie_header=self.client.cookie_header(), workers=1)
        self.assertEqual(again.downloaded, 0)
        self.assertEqual(again.skipped, 2)


if __name__ == "__main__":
    unittest.main()
