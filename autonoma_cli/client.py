"""Fachada del Campus Virtual: una sesion autenticada y sus datos.

El transporte vive en ``session``, el login y las cookies en ``auth``, y la
politica de llamadas con los WebMethods en ``api``. Este modulo solo compone
esas piezas, delega y describe la sesion para los comandos.
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import urljoin

from . import __version__, api, config
from .auth import AuthSession
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
        self._session = session if session is not None else CampusSession(
            self.base_url, timeout=timeout, delay=delay,
            cookies_path=cookies_file or str(config.cookies_path()),
            pinned_path=config.pinned_path(),
        )
        self._auth = AuthSession(self._session, self.login_url, self.headers)
        self._api = api.ApiContext(
            base_url=self.base_url,
            headers=self.headers,
            session=self._session,
            auth=self._auth,
            retries=self.retries,
        )

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

    def send(self, request: Any):
        return self._session.send(request)

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

    def call(
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

        return api.call.call(
            self._api,
            method,
            payload,
            page=page,
            allow_relogin=allow_relogin,
            retry_transient=retry_transient,
        )

    # -- datos ------------------------------------------------------------ #

    def get_courses(self) -> list[Course]:
        return api.methods.get_courses(self._api)

    def get_course_detail(self, group_id: int | str, session: int = 0) -> Any:
        return api.methods.get_course_detail(self._api, group_id, session)

    def ensure_student_code(self) -> str:
        """Lee el codigo de alumno si aun no lo tenemos.

        Con la cookie guardada no hay login y el codigo solo aparece en
        Default.aspx; sin el, el historial responde vacio.
        """

        return self._auth.ensure_student_code()

    def get_curricula(self, kind: int = 1) -> list[Mapping[str, Any]]:
        """Curriculas del alumno (1 = carrera, 2 = extraacademicos)."""

        return api.methods.get_curricula(self._api, kind)

    def get_history(self) -> list[Mapping[str, Any]]:
        """Cursos de todos los periodos: recorre cada curricula del alumno."""

        return api.methods.get_history(self._api)

    def get_grades(self, group_id: int | str) -> CourseGrades:
        """Criterios del periodo abierto (``getNotasAlumnoGrupo``)."""

        return api.methods.get_grades(self._api, group_id)

    def get_academic_summary(self) -> AcademicSummary:
        """Promedio oficial del tablero (``ObtenerDataAvanceCarrera``)."""

        return api.methods.get_academic_summary(self._api)

    def get_syllabus(self, group_id: int | str) -> list[SessionTopic]:
        return api.methods.get_syllabus(self._api, group_id)

    def get_schedule(self, group_id: int | str, *, course: str = "") -> list[ClassSession]:
        """Programacion del grupo: fechas, horarios y aula de cada sesion."""

        return api.methods.get_schedule(self._api, group_id, course=course)

    def get_session_resources(self, group_id: int | str, session: int) -> list[Resource]:
        return api.methods.get_session_resources(self._api, group_id, session)

    def active_session_resources(self, group_id: int | str) -> list[Resource]:
        """Recursos de la sesion activa, con la lectura que ya trae el curso.

        ``getInformationDetailCurso`` con ``nSesion=0`` devuelve el silabo y los
        recursos de la semana en curso en una sola peticion. Las carpetas traen
        su ``nSesion`` (docs/GUIA.md), asi que alcanza para no recorrer el resto.
        """

        return api.methods.active_session_resources(self._api, group_id)

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

        return api.methods.iter_session_resources(
            self._api,
            group_id,
            sessions,
            stop_after_empty=stop_after_empty,
            max_sessions=config.load_settings().max_sessions,
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

        return api.methods.iter_session_resources_lazy(
            self._api,
            group_id,
            sessions,
            stop_after_empty=stop_after_empty,
            max_sessions=config.load_settings().max_sessions,
        )

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

        return api.post_raw(self._api, body, content_type=content_type, page=page)

    def describe(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "authenticated": self._auth.authenticated,
            "student_code": self._auth.student_code,
            "cookies_file": self._session.cookies_path,
            "cookie_names": self._auth.cookie_names(),
        }
