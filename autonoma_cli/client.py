"""Cliente HTTP del Campus Virtual (ASP.NET Web Forms + WebMethods JSON).

Flujo:
  1. GET  /Campus/Login.aspx  -> campos ocultos (__VIEWSTATE, __EVENTVALIDATION...)
  2. POST /Campus/Login.aspx  -> cookies de sesion
  3. POST /Campus/Default.aspx/<metodo>  -> JSON {"d": ...}

Las cookies se guardan en disco para no repetir el login en cada comando.
"""

from __future__ import annotations

import json
import time
from typing import Any, Iterable, Iterator, Mapping, Sequence
from urllib.parse import urljoin
from urllib.request import Request

from . import __version__, config
from .auth import AuthSession, LOGIN_REDIRECT
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
        session: CampusSession | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.login_url = urljoin(self.base_url + "/", "Campus/Login.aspx")
        self.retries = max(1, int(retries))
        self.headers = {
            "User-Agent": user_agent,
            "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
        }
        self._session = session or CampusSession(
            self.base_url, timeout=timeout, delay=delay,
            cookies_path=cookies_file or str(config.cookies_path()),
            pinned_path=config.pinned_path(),
        )
        self._auth = AuthSession(self._session, self.login_url, self.headers)

    # -- infraestructura -------------------------------------------------- #

    @property
    def authenticated(self) -> bool:
        return self._auth.authenticated

    @property
    def student_code(self) -> str:
        return self._auth.student_code

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

        return self._auth.authenticate(username, password, force_login=force_login)

    def login(self, username: str, password: str) -> None:
        self._auth.login(username, password)

    def forget_cookies(self) -> bool:
        """Borra la cookie guardada en disco y vacia el jar en memoria."""

        return self._auth.logout()

    def cookie_header(self) -> str:
        """Cabecera Cookie para descargas fuera de esta sesion (hilos)."""

        return self._auth.cookie_header()

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

        if LOGIN_REDIRECT.search(final_url):
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
                if not self._auth.authenticated:
                    self._auth.relogin()
                return self._call_once(method, payload, page)
            except SessionExpiredError:
                self._auth.expire()
                if allow_relogin:
                    self._auth.relogin()
                    return self._call_once(method, payload, page)
                raise
            except CampusHTTPError as exc:
                if exc.status_code == 401:
                    # La cookie vencio sin redirigir al login: el campus responde 401.
                    self._auth.expire()
                    if allow_relogin:
                        self._auth.relogin()
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

        return self._auth.ensure_student_code()

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
        self._auth.expire()
        self._auth.relogin()
        return self._send_upload(request)

    def _send_upload(self, request: Request) -> str:
        with self._session.send(request) as response:
            final_url = response.geturl()
            raw = response.read().decode("utf-8", "replace")
        if LOGIN_REDIRECT.search(final_url):
            raise SessionExpiredError("La sesion del campus expiro.")
        return raw

    def describe(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "authenticated": self._auth.authenticated,
            "student_code": self._auth.student_code,
            "cookies_file": self._session.cookies_path,
            "cookie_names": self._auth.cookie_names(),
        }
