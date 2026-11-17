"""Contrato de subida del campus: formulario multipart, XML y respuestas.

Todo lo que el campus espera y devuelve vive aca para poder probarlo sin red
(docs/API.md, seccion 10). ``uploader.py`` arma el plan y orquesta la corrida.

- ``--carpeta``: ``Doc_InsertarRecurso`` con ``<Recursos>`` (nDocLinTipo 2).
- ``--tarea``: ``Alu_InsertarTarea`` con ``<TAREA>`` (exito: nRespTarea > 1).
"""

from __future__ import annotations

from typing import Any, Mapping
from xml.sax.saxutils import escape

from .api import parse_json_text, unwrap
from .errors import ProtocolError

UPLOAD_PAGE = "/GlobalAplication/FileUpload.ashx"
RESOURCE_PAGE = "/CampusVirtual/ua/Docente/MisCursos/Doc_CursosActuales.aspx"
# Alu_CursosActuales expone Alu_InsertarTarea y setCarpetaRecurso (Mongo).
TASK_PAGE = "/CampusVirtual/ua/Alumno/MisCursos/Alu_CursosActuales.aspx"
# Un nombre de archivo de Windows: mas largo ya es una pagina o basura.
MAX_SAVED_NAME = 255


# --------------------------------------------------------------------------- #
# Multipart
# --------------------------------------------------------------------------- #


def multipart_body(
    data: bytes,
    filename: str,
    *,
    boundary: str,
    folder: str = "",
    path: str = "/Uploads",
    param0: str = "",
) -> bytes:
    """Cuerpo multipart del formulario del campus, en el orden que espera."""

    parts = [
        _field(boundary, "folder0", folder),
        _file_part(boundary, "file0", filename, data),
    ]
    if param0:
        parts.append(_field(boundary, "param0", param0))
    parts.append(_field(boundary, "path0", path))
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts)


def _field(boundary: str, name: str, value: str) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode("utf-8")


def _file_part(boundary: str, name: str, filename: str, data: bytes) -> bytes:
    safe = filename.replace('"', "%22").replace("\r", "").replace("\n", "")
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="{safe}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    return header + data + b"\r\n"


# --------------------------------------------------------------------------- #
# XML
# --------------------------------------------------------------------------- #


def resource_xml(plan: Any, saved: str) -> str:
    """``<Recursos>`` de una carpeta compartida (nDocLinTipo 2 = archivo)."""

    target = plan.target
    return (
        "<Recursos>"
        f"<url>{escape(saved)}</url>"
        "<nDocLinTipo>2</nDocLinTipo>"
        f"<titulo>{escape(plan.title)}</titulo>"
        f"<descripcion>{escape(plan.description)}</descripcion>"
        "<Accion>A1</Accion>"
        f"<nForoSesion>{target.session}</nForoSesion>"
        "<cForoPadre>0</cForoPadre>"
        "<nEstado>1</nEstado>"
        f"<cDocCodigo>{escape(target.course_code)}</cDocCodigo>"
        "<nSubTipoMaterial>65003210</nSubTipoMaterial>"
        "<nCarCodigo>2</nCarCodigo>"
        f"<nDocLinGrupo>{target.number}</nDocLinGrupo>"
        "<nPerRelacion>1</nPerRelacion>"
        "<encualquiermomento>0</encualquiermomento>"
        "</Recursos>"
    )


def task_xml(plan: Any, saved: str) -> str:
    """``<TAREA>`` de una entrega; ``IDDirectory`` y ``cUuid`` van vacios."""

    target = plan.target
    return (
        "<TAREA>"
        f"<url>{escape(saved)}</url>"
        f"<titulo>{escape(plan.title)}</titulo>"
        f"<descripcion>{escape(plan.description)}</descripcion>"
        f"<cDocCodigo>{escape(target.course_code)}</cDocCodigo>"
        f"<nDocLinNum>{target.number}</nDocLinNum>"
        f"<nGruCurso>{target.group_id}</nGruCurso>"
        "<Accion>A1</Accion>"
        "<nRespTarea>0</nRespTarea>"
        "<IDDirectory></IDDirectory>"
        "<cUuid></cUuid>"
        "</TAREA>"
    )


def folder_sync_payload(
    plan: Any, result: Any, student_code: str, *, timestamp: str
) -> dict[str, Any]:
    """Cuerpo de ``setCarpetaRecurso``: ``silaboId`` y ``sesionId`` van vacios."""

    return {
        "nDocLinNum": plan.target.number,
        "nGruCodigo": plan.target.group_id,
        "carpetaInformation": {
            "cDocLinUrl": result.saved_name,
            "Archivo": result.saved_name,
            "cPerCodigo": student_code,
            "cDocLinComentario": plan.description,
            "cDocLinDescripcion": plan.title,
            "nDocLinNum": result.resource_id,
            "nDocLinGrupo": plan.target.number,
            "autor": "",
            "fechaRegistro": timestamp,
        },
        "silaboId": "",
        "sesionId": "",
    }


# --------------------------------------------------------------------------- #
# Respuestas
# --------------------------------------------------------------------------- #


def saved_name(raw: str) -> str:
    """Nombre con el que el campus guardo el archivo (texto o ``{"d": ...}``).

    Una pagina HTML con estado 200 no es un nombre: se rechaza antes de usarlo.
    """

    payload: Any = parse_json_text(raw)
    if isinstance(payload, Mapping):
        payload = payload.get("d")
    value = str(payload or "").strip().strip('"')
    if not value:
        raise ProtocolError("La subida no devolvio el nombre del archivo guardado.")
    bad = any(char in value for char in '<>\r\n\\/') or len(value) > MAX_SAVED_NAME
    if bad:
        raise ProtocolError(
            "La subida no devolvio un nombre de archivo: parece una pagina de "
            f"error del campus ({value[:60]!r}). Vuelve a intentarlo con: autonoma login"
        )
    return value


def number(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def records(payload: Any, key: str) -> list[Mapping[str, Any]]:
    """Lista de filas de una respuesta que puede venir anidada o como texto."""

    data = unwrap(payload)
    if isinstance(data, Mapping):
        value = data.get(key)
        if isinstance(value, str):
            value = parse_json_text(value)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    raise ProtocolError(f"La respuesta no trae {key}.")


def reason(record: Mapping[str, Any]) -> str:
    """Mensaje del campus para un rechazo, si lo mando."""

    for key in ("cMensaje", "cDescripcion", "mensaje", "descripcion", "cDetalle"):
        value = record.get(key)
        if value:
            return str(value)
    return "el campus no explico el motivo"
