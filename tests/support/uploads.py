"""Cliente de mentira para probar `entregar` sin red."""

from __future__ import annotations

from typing import Any

from autonoma_cli.errors import CampusError
from autonoma_cli.models import Course, Resource

from .fixtures import BASE, courses

FOLDER = 209902
TASK = 209901
SESSION = 10


def folder_resource(number: int = FOLDER, session: int = SESSION) -> Resource:
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


class UploadClient:
    """Misma superficie que usa `entregar`, con las respuestas del campus fijas."""

    base_url = BASE
    student_code = "2024000001"

    def __init__(
        self,
        *,
        resource_state: Any = 1,
        task_response: Any = 2099011,
        sync_error: str = "",
        folders: list[Resource] | None = None,
        folder_active: bool = True,
        folder_session: int = SESSION,
        student_error: str = "",
    ) -> None:
        self.resource_state = resource_state
        self.task_response = task_response
        self.sync_error = sync_error
        self.folders = [folder_resource()] if folders is None else folders
        self.folder_active = folder_active
        self.folder_session = folder_session
        self.student_error = student_error
        self.uploads: list[bytes] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.reads: list[str] = []

    def get_courses(self) -> list[Course]:
        self.reads.append("cursos")
        return courses()

    def get_history(self) -> list[dict[str, Any]]:
        return []

    def active_session_resources(self, group_id: object) -> list[Resource]:
        self.reads.append("sesion activa")
        return self.folders if self.folder_active else []

    def iter_session_resources_lazy(self, group_id: object):
        self.reads.append("sesiones")
        yield self.folder_session, self.folders

    def ensure_student_code(self) -> str:
        if self.student_error:
            raise CampusError(self.student_error)
        return self.student_code

    def upload_file(self, body: bytes, *, content_type: str, page: str = "") -> str:
        self.uploads.append(body)
        return "209901_ENTREGA.zip"

    def call(
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
        if method == "setCarpetaRecurso":
            if self.sync_error:
                raise CampusError(self.sync_error)
            return 1
        if method == "Alu_InsertarTarea":
            return {"d": self.task_response}
        raise AssertionError(f"llamada inesperada al campus: {method}")
