"""Cliente HTTP del Campus Virtual (ASP.NET Web Forms + WebMethods JSON).

Flujo:
  1. GET  /Campus/Login.aspx  -> campos ocultos (__VIEWSTATE, __EVENTVALIDATION...)
  2. POST /Campus/Login.aspx  -> cookies de sesion
  3. POST /Campus/Default.aspx/<metodo>  -> JSON {"d": ...}

Las cookies se guardan en disco para no repetir el login en cada comando.
"""

from __future__ import annotations

import json
import re
import time
from html.parser import HTMLParser
from http.cookiejar import Cookie, LWPCookieJar, LoadError
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

from . import __version__, config
from .errors import (
    AuthenticationError,
    CampusError,
    CampusHTTPError,
    ProtocolError,
    SessionExpiredError,
)
from .models import ClassSession, Course, Resource, SessionTopic, strip_html

DEFAULT_BASE_URL = config.DEFAULT_BASE_URL
DEFAULT_USER_AGENT = f"autonoma-cli/{__version__} (+uso-personal)"
PERFIL_ALUMNO = 13

_LOGIN_REDIRECT = re.compile(r"/Campus/Login\.aspx(?:$|[?#])", re.I)
_FAILURE_TEXT = re.compile(r'id="FailureText"[^>]*>(.*?)</span>', re.I | re.S)


class LoginPageParser(HTMLParser):
    """Extrae el action del formulario y sus campos ocultos.

    El HTML del campus repite el atributo ``name`` en algunos inputs
    (``name="txtUsuario" ... name="email-username"``). Por eso se toma la
    PRIMERA aparicion de cada atributo y no un ``dict(attrs)``.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.hidden: dict[str, str] = {}
        self.submit: dict[str, str] = {}
        self._form_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values: dict[str, str] = {}
        for key, value in attrs:
            if key and key not in values:
                values[key] = value or ""

        if tag == "form":
            if self.action is None or values.get("id") == "frmLogin" or values.get("name") == "frmLogin":
                self.action = values.get("action", "")
            self._form_depth += 1
            return

        name = values.get("name", "").strip()
        if tag != "input" or not name:
            return

        input_type = (values.get("type") or "text").lower()
        if input_type == "hidden":
            self.hidden[name] = values.get("value", "")
        elif input_type in {"submit", "button"}:
            self.submit[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form_depth:
            self._form_depth -= 1


def unwrap(payload: Any) -> Any:
    """Desenvuelve ``{"d": ...}``, incluso cuando ``d`` es un string JSON."""

    if not isinstance(payload, Mapping) or "d" not in payload:
        return payload
    value = payload["d"]
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _extract_student_code(html: str) -> str:
    patterns = (
        r'id="cPerCodigo"[^>]*value="([^"]+)"',
        r'id="txtcPerCodigoLog"[^>]*value="([^"]+)"',
        r'(?:cPerCodigo|CPERCODIGO)\s*[:=]\s*["\']([^"\']+)',
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return match.group(1).strip()
    return ""


def _as_records(data: Any) -> list[Mapping[str, Any]]:
    data = unwrap(data)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        for key in ("recursos", "items", "data", "result"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, Mapping)]
    return []


class CampusClient:
    """Sesion autenticada contra el campus."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = 30.0,
        delay: float = 0.5,
        user_agent: str = DEFAULT_USER_AGENT,
        cookies_file: str | None = None,
        retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.login_url = urljoin(self.base_url + "/", "Campus/Login.aspx")
        self.timeout = float(timeout)
        self.delay = max(0.0, float(delay))
        self.retries = max(1, int(retries))
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        }
        self._cookies_file = cookies_file or str(config.cookies_path())
        self._jar = LWPCookieJar(self._cookies_file)
        self._opener = build_opener(HTTPCookieProcessor(self._jar))
        self._default_url = urljoin(self.base_url + "/", "Campus/Default.aspx")
        self._authenticated = False
        self._credentials: tuple[str, str] | None = None
        self._last_request = 0.0
        self.student_code = ""

    # -- infraestructura -------------------------------------------------- #

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def referer(self) -> str:
        return self._default_url

    def _wait(self) -> None:
        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()

    def _open(self, request: Request):
        self._wait()
        try:
            return self._opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            raise CampusHTTPError(f"El campus respondio HTTP {exc.code}.", exc.code) from exc
        except URLError as exc:
            raise CampusError(f"No se pudo conectar con el campus: {exc.reason}.") from exc
        except TimeoutError as exc:
            raise CampusError("La conexion con el campus agoto el tiempo de espera.") from exc

    def close(self) -> None:
        try:
            self._opener.close()
        except Exception:  # noqa: BLE001 - el opener no siempre lo implementa
            pass

    # -- sesion ----------------------------------------------------------- #

    def authenticate(self, username: str, password: str, *, force_login: bool = False) -> bool:
        """Reutiliza la cookie guardada o inicia sesion.

        Devuelve True si hubo un login nuevo (util para informar al usuario).
        """

        self._credentials = (username, password)
        if not force_login and self.load_cookies():
            self._authenticated = True
            return False
        self.login(username, password)
        return True

    def login(self, username: str, password: str) -> None:
        username = (username or "").strip()
        if not username or not password:
            raise AuthenticationError("Usuario y contrasena son obligatorios.")
        self._credentials = (username, password)

        with self._open(Request(self.login_url, headers=self.headers)) as response:
            html = response.read().decode("utf-8", "replace")

        parser = LoginPageParser()
        parser.feed(html)
        action = urljoin(self.login_url, parser.action or self.login_url)
        data = dict(parser.hidden)
        data["txtUsuario"] = username
        data["txtPassword"] = password
        if "btn_ingresar" in parser.submit:
            data["btn_ingresar"] = parser.submit["btn_ingresar"]
        elif parser.submit:
            name, value = next(iter(parser.submit.items()))
            data[name] = value
        else:
            data["btn_ingresar"] = "Ingresar"

        request = Request(
            action,
            data=urlencode(data).encode("utf-8"),
            headers={
                **self.headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self.login_url,
            },
            method="POST",
        )
        with self._open(request) as response:
            final_url = response.geturl()
            body = response.read().decode("utf-8", "replace")

        if _LOGIN_REDIRECT.search(final_url):
            match = _FAILURE_TEXT.search(body)
            detail = strip_html(match.group(1)) if match else ""
            raise AuthenticationError(
                "El campus rechazo las credenciales."
                + (f" Mensaje del campus: {detail}" if detail else "")
            )
        if "/Campus/Default.aspx" not in final_url and 'id="cPerCodigo"' not in body:
            raise AuthenticationError("El login no llego al panel del campus (posible CAPTCHA o MFA).")

        self._default_url = final_url
        self.student_code = _extract_student_code(body)
        self._authenticated = True
        self.save_cookies()

    def _relogin(self) -> None:
        if not self._credentials:
            raise SessionExpiredError(
                "La sesion del campus expiro y no hay credenciales para renovarla. "
                "Ejecuta: autonoma login"
            )
        username, password = self._credentials
        self.login(username, password)

    def save_cookies(self) -> None:
        try:
            config.ensure_home()
            self._jar.save(ignore_discard=True, ignore_expires=True)
        except (OSError, LoadError):
            pass

    def load_cookies(self) -> bool:
        path = self._cookies_file
        try:
            self._jar.load(ignore_discard=True, ignore_expires=False)
        except (OSError, LoadError):
            return False
        return any(not cookie.is_expired() for cookie in self._jar)

    def forget_cookies(self) -> bool:
        """Borra la cookie guardada en disco y vacia el jar en memoria."""

        self._authenticated = False
        self.student_code = ""
        removed = False
        try:
            import os

            if os.path.exists(self._cookies_file):
                os.unlink(self._cookies_file)
                removed = True
        except OSError:
            pass
        self._jar.clear()
        return removed

    def cookie_header(self) -> str:
        """Cabecera Cookie para descargas fuera de esta sesion (hilos)."""

        pairs = []
        for cookie in self._jar:
            if isinstance(cookie, Cookie) and not cookie.is_expired():
                pairs.append(f"{cookie.name}={cookie.value}")
        return "; ".join(pairs)

    # -- WebMethods -------------------------------------------------------- #

    def _call_once(self, method: str, payload: Mapping[str, Any], page: str) -> Any:
        page_url = urljoin(self.base_url + "/", page.lstrip("/"))
        endpoint = f"{page_url.rstrip('/')}/{method}"
        request = Request(
            endpoint,
            data=json.dumps(dict(payload), ensure_ascii=False).encode("utf-8"),
            headers={
                **self.headers,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/json; charset=utf-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self._default_url,
            },
            method="POST",
        )
        with self._open(request) as response:
            final_url = response.geturl()
            raw = response.read().decode("utf-8", "replace")

        if _LOGIN_REDIRECT.search(final_url):
            raise SessionExpiredError("La sesion del campus expiro.")
        if not raw.strip():
            return None
        try:
            payload_json = json.loads(raw)
        except json.JSONDecodeError as exc:
            snippet = raw[:160].replace("\n", " ")
            raise ProtocolError(f"{method} no devolvio JSON: {snippet!r}") from exc
        return unwrap(payload_json)

    def _call(
        self,
        method: str,
        payload: Mapping[str, Any] | None = None,
        *,
        page: str = "/Campus/Default.aspx",
        allow_relogin: bool = True,
    ) -> Any:
        payload = payload or {}
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                if not self._authenticated:
                    self._relogin()
                return self._call_once(method, payload, page)
            except SessionExpiredError:
                self._authenticated = False
                if allow_relogin:
                    self._relogin()
                    return self._call_once(method, payload, page)
                raise
            except CampusHTTPError as exc:
                if exc.status_code == 401:
                    # La cookie vencio sin redirigir al login: el campus responde 401.
                    self._authenticated = False
                    if allow_relogin:
                        self._relogin()
                        return self._call_once(method, payload, page)
                    raise SessionExpiredError("La sesion del campus expiro.") from exc
                if exc.status_code in {500, 502, 503, 504} and attempt < self.retries:
                    last_error = exc
                    time.sleep(1.5 * attempt)
                    continue
                raise
            except CampusError as exc:
                if isinstance(exc, (AuthenticationError, ProtocolError)):
                    raise
                if attempt < self.retries:
                    last_error = exc
                    time.sleep(1.5 * attempt)
                    continue
                raise
        raise last_error or CampusError(f"{method} fallo sin detalle.")

    # -- datos ------------------------------------------------------------ #

    def get_courses(self) -> list[Course]:
        data = self._call("Alu_ObtenerCursosActuales", {})
        if not isinstance(data, list):
            raise ProtocolError("La lista de cursos no tiene el formato esperado.")
        return [
            Course.from_api(item, self.base_url)
            for item in data
            if isinstance(item, Mapping) and item.get("nGruCodigo")
        ]

    def get_course_detail(self, group_id: int | str, session: int = 0) -> Any:
        return self._call(
            "getInformationDetailCurso",
            {
                "nGruCodigo": group_id,
                "nSesion": int(session),
                "nPerfil": PERFIL_ALUMNO,
            },
        )

    def ensure_student_code(self) -> str:
        """Lee el codigo de alumno si aun no lo tenemos.

        Con la cookie guardada no hay login y el codigo solo aparece en
        Default.aspx; sin el, el historial responde vacio.
        """

        if self.student_code:
            return self.student_code
        request = Request(
            self._default_url,
            headers={**self.headers, "Referer": self._default_url},
        )
        with self._open(request) as response:
            html = response.read().decode("utf-8", "replace")
        self.student_code = _extract_student_code(html)
        return self.student_code

    def get_curricula(self, kind: int = 1) -> list[Mapping[str, Any]]:
        """Curriculas del alumno (1 = carrera, 2 = extraacademicos)."""

        data = self._call(
            "obtenerUniOrgCurriculo",
            {"cPerCodigo": self.ensure_student_code(), "nTipCur": kind},
            page="/Modulos/Campus/MisCursos/Ca_Mc_CursosMatriculados.aspx",
        )
        return _as_records(data)

    def get_history(self) -> list[Mapping[str, Any]]:
        """Cursos de todos los periodos: recorre cada curricula del alumno."""

        rows: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for curriculum in self.get_curricula():
            data = self._call(
                "ObtenerCursosByCurricula",
                {
                    "nCurCodigo": curriculum.get("nCurCodigo"),
                    "cPerCodigo": "",
                    "cTablas": "HISTORIAL_CURSOS,PERIODO_HISTORIAL_CURSOS",
                },
                page="/CampusVirtual/ua/Alumno/MisCursos/Alu_HistorialCursos.aspx",
            )
            if not isinstance(data, Mapping):
                continue
            for row in _as_records(data.get("HISTORIAL_CURSOS")):
                key = str(row.get("nGruCodigo"))
                if key not in seen:
                    seen.add(key)
                    rows.append(row)
        return rows

    def get_syllabus(self, group_id: int | str) -> list[SessionTopic]:
        data = self.get_course_detail(group_id, 0)
        topics: Iterable[Any] = ()
        if isinstance(data, Mapping):
            raw = data.get("silabo")
            if isinstance(raw, list):
                topics = raw
        return [SessionTopic.from_api(item) for item in topics if isinstance(item, Mapping)]

    def get_schedule(self, group_id: int | str, *, course: str = "") -> list[ClassSession]:
        """Programacion del grupo: fechas, horarios y aula de cada sesion."""

        data = self._call("getProgramacionAlumnoGrupo", {"nGruCodigo": group_id})
        return [
            ClassSession.from_api(item, group_id=group_id, course=course)
            for item in _as_records(data)
        ]

    def get_session_resources(self, group_id: int | str, session: int) -> list[Resource]:
        data = self.get_course_detail(group_id, session)
        records = _as_records(data)
        return [
            Resource.from_api(item, self.base_url, session=session)
            for item in records
        ]

    def iter_session_resources(
        self,
        group_id: int | str,
        sessions: Sequence[int] | None = None,
        *,
        stop_after_empty: int = 2,
    ) -> list[tuple[int, list[Resource]]]:
        """Recorre las sesiones y devuelve (numero, recursos) de cada una.

        Si no se indican sesiones, se usan las del silabo; si el silabo no
        viene, se prueban 1..max_sessions y se corta tras N sesiones vacias.
        """

        numbers = list(sessions) if sessions else [
            topic.number for topic in self.get_syllabus(group_id) if topic.number
        ]
        if not numbers:
            numbers = list(range(1, config.load_settings().max_sessions + 1))
            limit = stop_after_empty
        else:
            limit = 0

        result: list[tuple[int, list[Resource]]] = []
        empty_run = 0
        for number in numbers:
            resources = [item for item in self.get_session_resources(group_id, number) if item.kind != 0]
            result.append((number, resources))
            if resources:
                empty_run = 0
            else:
                empty_run += 1
                if limit and empty_run >= limit:
                    break
        return result

    def describe(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "authenticated": self.authenticated,
            "student_code": self.student_code,
            "cookies_file": self._cookies_file,
            "cookie_names": [cookie.name for cookie in self._jar],
        }
