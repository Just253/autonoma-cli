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
from http.cookiejar import Cookie, LoadError
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import urlencode, urljoin
from urllib.request import Request

from . import __version__, config
from .errors import (
    AuthenticationError,
    CampusError,
    CampusHTTPError,
    ProtocolError,
    SessionExpiredError,
)
from .models import (
    AcademicSummary,
    ClassSession,
    Course,
    CourseGrades,
    Resource,
    SessionTopic,
    strip_html,
)
from .session import CampusSession

DEFAULT_BASE_URL = config.DEFAULT_BASE_URL
DEFAULT_USER_AGENT = f"autonoma-cli/{__version__} (+uso-personal)"
PERFIL_ALUMNO = 13
TABLERO_PAGE = "/Campus/ua/Tablero/Perfil/Camp_Virt_Perfil.aspx"
# cTablas exacto del tablero (docs/API.md seccion 8): cada nombre vuelve como clave.
TABLERO_TABLES = (
    "Malla_Curricular,Malla_Curricular_grafPromedioNotaByCiclo,"
    "Malla_Curricular_grafAvanceCarrera,Malla_Curricular_grafTipoCurso,"
    "DatosPersonales,Competencias,PuestoAcademico"
)

_LOGIN_REDIRECT = re.compile(r"/Campus/Login\.aspx(?:$|[?#])", re.I)
_FAILURE_TEXT = re.compile(r'id="FailureText"[^>]*>(.*?)</span>', re.I | re.S)
# El campus obliga a rotar la contrasena y manda a CambioContrasena.aspx antes
# de dejar entrar al panel; no es un fallo de credenciales ni CAPTCHA/MFA.
_PASSWORD_CHANGE = re.compile(r"/Campus/CambioContrasena\.aspx", re.I)


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


def parse_json_text(raw: str) -> Any:
    """Devuelve el JSON que trae ``raw`` y lo desenvuelve; si no es JSON, el texto.

    Lo usan las subidas: ``FileUpload.ashx`` contesta el nombre guardado como
    texto pelado, pero algunas versiones lo mandan como ``{"d": ...}``.
    """

    try:
        return unwrap(json.loads(raw))
    except (TypeError, ValueError):
        return raw


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
        self.retries = max(1, int(retries))
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        }
        self._session = CampusSession(
            self.base_url,
            timeout=timeout,
            delay=delay,
            cookies_path=cookies_file or str(config.cookies_path()),
            pinned_path=config.pinned_path(),
        )
        self._authenticated = False
        self._credentials: tuple[str, str] | None = None
        self.student_code = ""

    # -- infraestructura -------------------------------------------------- #

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def referer(self) -> str:
        return self._session.home_url

    @property
    def timeout(self) -> float:
        return self._session.timeout

    @property
    def delay(self) -> float:
        return self._session.delay

    def close(self) -> None:
        self._session.close()

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

        with self._session.send(Request(self.login_url, headers=self.headers)) as response:
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
        with self._session.send(request) as response:
            final_url = response.geturl()
            body = response.read().decode("utf-8", "replace")

        if _LOGIN_REDIRECT.search(final_url):
            match = _FAILURE_TEXT.search(body)
            detail = strip_html(match.group(1)) if match else ""
            raise AuthenticationError(
                "El campus rechazo las credenciales."
                + (f" Mensaje del campus: {detail}" if detail else "")
            )
        if _PASSWORD_CHANGE.search(final_url):
            raise AuthenticationError(
                "El campus acepto el usuario y la contrasena, pero exige cambiarla "
                "antes de dar acceso al panel. Entra al campus, actualizala y "
                "repite: autonoma login"
            )
        if "/Campus/Default.aspx" not in final_url and 'id="cPerCodigo"' not in body:
            raise AuthenticationError("El login no llego al panel del campus (posible CAPTCHA o MFA).")

        self._session.home_url = final_url
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
            self._session.jar.save(ignore_discard=True, ignore_expires=True)
        except (OSError, LoadError):
            pass

    def load_cookies(self) -> bool:
        try:
            self._session.jar.load(ignore_discard=True, ignore_expires=False)
        except (OSError, LoadError):
            return False
        return any(not cookie.is_expired() for cookie in self._session.jar)

    def forget_cookies(self) -> bool:
        """Borra la cookie guardada en disco y vacia el jar en memoria."""

        self._authenticated = False
        self.student_code = ""
        removed = False
        try:
            import os

            if os.path.exists(self._session.cookies_path):
                os.unlink(self._session.cookies_path)
                removed = True
        except OSError:
            pass
        self._session.jar.clear()
        return removed

    def cookie_header(self) -> str:
        """Cabecera Cookie para descargas fuera de esta sesion (hilos)."""

        pairs = []
        for cookie in self._session.jar:
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
                "Referer": self._session.home_url,
            },
            method="POST",
        )
        with self._session.send(request) as response:
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
        retry_transient: bool = True,
    ) -> Any:
        """Llama a un WebMethod y desenvuelve la respuesta.

        ``retry_transient=False`` deja un solo intento ante 5xx o red caida:
        los registros de entrega (``Doc_InsertarRecurso``, ``Alu_InsertarTarea``)
        no son idempotentes y repetirlos puede duplicar el envio. Solo se
        reintenta por autenticacion (401 o sesion vencida), que no llego a
        ejecutar el metodo.
        """

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
                if retry_transient and exc.status_code in {500, 502, 503, 504} and attempt < self.retries:
                    last_error = exc
                    time.sleep(1.5 * attempt)
                    continue
                raise
            except CampusError as exc:
                if isinstance(exc, (AuthenticationError, ProtocolError)) or not retry_transient:
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
            self._session.home_url,
            headers={**self.headers, "Referer": self._session.home_url},
        )
        with self._session.send(request) as response:
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

    def get_grades(self, group_id: int | str) -> CourseGrades:
        """Criterios del periodo abierto (``getNotasAlumnoGrupo``)."""

        data = self._call("getNotasAlumnoGrupo", {"nGruCodigo": group_id})
        if not isinstance(data, Mapping):
            raise ProtocolError("Las notas del curso no tienen el formato esperado.")
        return CourseGrades.from_api(data, group_id=group_id)

    def get_academic_summary(self) -> AcademicSummary:
        """Promedio oficial del tablero (``ObtenerDataAvanceCarrera``)."""

        student = self.ensure_student_code()
        current = self._call(
            "ObtenerCurrriculasActuales", {"cPerCodigo": student}, page=TABLERO_PAGE
        )
        records = _as_records(current)
        if not records and isinstance(current, Mapping):
            # Sin clave conocida: la primera lista de filas es la de curriculas.
            records = [
                item
                for value in current.values()
                if isinstance(value, list)
                for item in value
                if isinstance(item, Mapping)
            ]
        enrollment = records[0].get("nPerAluRegCodigo") if records else None
        if not enrollment:
            raise ProtocolError("El tablero no devolvio la matricula del alumno.")
        data = self._call(
            "ObtenerDataAvanceCarrera",
            {"cPerCodigo": "", "nPerAluRegCodigo": enrollment, "cTablas": TABLERO_TABLES},
            page=TABLERO_PAGE,
        )
        if not isinstance(data, Mapping):
            raise ProtocolError("El avance de carrera no tiene el formato esperado.")
        return AcademicSummary.from_api(data)

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

    def active_session_resources(self, group_id: int | str) -> list[Resource]:
        """Recursos de la sesion activa, con la lectura que ya trae el curso.

        ``getInformationDetailCurso`` con ``nSesion=0`` devuelve el silabo y los
        recursos de la semana en curso en una sola peticion. Las carpetas traen
        su ``nSesion`` (docs/GUIA.md), asi que alcanza para no recorrer el resto.
        """

        return self.get_session_resources(group_id, 0)

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

        return list(
            self.iter_session_resources_lazy(
                group_id, sessions, stop_after_empty=stop_after_empty
            )
        )

    def iter_session_resources_lazy(
        self,
        group_id: int | str,
        sessions: Sequence[int] | None = None,
        *,
        stop_after_empty: int = 2,
    ) -> Iterator[tuple[int, list[Resource]]]:
        """Como ``iter_session_resources`` pero pide una sesion por vez.

        El consumidor puede cortar en la primera coincidencia: las sesiones que
        faltan no se piden. Es la version que usa ``entregar`` para buscar una
        carpeta sin recorrer el curso entero.
        """

        if sessions:
            numbers = list(sessions)
            limit = 0
        else:
            numbers = [
                topic.number for topic in self.get_syllabus(group_id) if topic.number
            ]
            if numbers:
                limit = 0
            else:
                numbers = list(range(1, config.load_settings().max_sessions + 1))
                limit = stop_after_empty

        empty_run = 0
        for number in numbers:
            resources = [
                item
                for item in self.get_session_resources(group_id, number)
                if item.kind != 0
            ]
            yield number, resources
            if resources:
                empty_run = 0
            else:
                empty_run += 1
                if limit and empty_run >= limit:
                    break

    def upload_file(
        self,
        body: bytes,
        *,
        content_type: str,
        page: str = "/GlobalAplication/FileUpload.ashx",
    ) -> str:
        """Manda un cuerpo multipart ya armado y devuelve el texto de la respuesta.

        Es una sola subida: solo se repite si la sesion habia vencido y el
        campus no llego a guardar nada (redireccion al login o HTTP 401).
        """

        url = urljoin(self.base_url + "/", page.lstrip("/"))
        request = Request(
            url,
            data=body,
            headers={
                **self.headers,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": content_type,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self._session.home_url,
            },
            method="POST",
        )
        try:
            return self._send_upload(request)
        except SessionExpiredError:
            pass
        except CampusHTTPError as exc:
            if exc.status_code != 401:
                raise
        self._authenticated = False
        self._relogin()
        return self._send_upload(request)

    def _send_upload(self, request: Request) -> str:
        with self._session.send(request) as response:
            final_url = response.geturl()
            raw = response.read().decode("utf-8", "replace")
        if _LOGIN_REDIRECT.search(final_url):
            raise SessionExpiredError("La sesion del campus expiro.")
        return raw

    def describe(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "authenticated": self.authenticated,
            "student_code": self.student_code,
            "cookies_file": self._session.cookies_path,
            "cookie_names": [cookie.name for cookie in self._session.jar],
        }
