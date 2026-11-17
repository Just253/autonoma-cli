"""Subida de un archivo al campus: destino, plan y corrida.

El contrato (multipart, XML y respuestas) vive en ``uploadform.py``; aca se
valida lo que pidio el usuario y se hace una subida y un registro. Si el campus
rechaza, se informa y se sale: no se reintenta el registro ni se cae a otro
destino.

Todo lo demas de la CLI sigue siendo de solo lectura.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from . import uploadform
from .api import unwrap
from .client import CampusClient
from .errors import CampusError, UsageError
from .models import Course, Resource, UploadPlan, UploadResult, UploadTarget
from .uploadcheck import precheck

FOLDER_TYPE = 1


# --------------------------------------------------------------------------- #
# Destino
# --------------------------------------------------------------------------- #


def target_for(
    client: CampusClient,
    course: Course,
    *,
    folder: int | None = None,
    task: int | None = None,
    session: int | None = None,
) -> UploadTarget:
    """Destino pedido en la linea de comandos: exactamente uno de los dos.

    ``session`` solo vale con ``--carpeta``: salta la busqueda de la semana y
    sus lecturas del curso.
    """

    if (folder is None) == (task is None):
        raise UsageError("Indica exactamente un destino: --carpeta N o --tarea N.")
    code = (course.upload_code or "").strip()
    if not code:
        raise UsageError(
            "El curso no trae codigo (cDocCodigo); sin el, el campus no registra la "
            "entrega. Nombra el curso por su nGruCodigo."
        )
    if task is not None:
        if session is not None:
            raise UsageError("--sesion solo vale con --carpeta: en tareas la semana no se usa.")
        if int(task) <= 0:
            raise UsageError("--tarea necesita el nDocLinNum de la tarea (numero positivo).")
        return UploadTarget("tarea", int(task), 0, course.group_id, code)
    number = int(folder)
    if number <= 0:
        raise UsageError("--carpeta necesita el nDocLinNum de la carpeta (numero positivo).")
    if session is not None:
        if int(session) <= 0:
            raise UsageError("--sesion necesita la semana de la carpeta (numero positivo).")
        return UploadTarget("carpeta", number, int(session), course.group_id, code)
    week = folder_session(client, course.group_id, number)
    return UploadTarget("carpeta", number, week, course.group_id, code)


def folder_session(client: CampusClient, group_id: int | str, folder: int) -> int:
    """Semana de la carpeta compartida: el XML exige ``nForoSesion``.

    Primero mira la sesion activa, que ``get_course_detail(group_id, 0)`` ya
    devuelve en una sola lectura; si la carpeta no esta ahi, recorre las
    sesiones de a una y corta en la primera coincidencia. Si no aparece, se
    para: una sesion inventada registraria el archivo en otra semana.
    """

    found = _folder_session_in(client.active_session_resources(group_id), folder)
    if found is not None:
        return found
    for session, resources in client.iter_session_resources_lazy(group_id):
        found = _folder_session_in(resources, folder, fallback=session)
        if found is not None:
            return found
    raise UsageError(
        f"No encontre la carpeta {folder} en el curso {group_id}. "
        "Revisa su nDocLinNum con: autonoma recursos <curso>; si la sabes, "
        "agrega --sesion <semana> para saltar la busqueda."
    )


def _folder_session_in(
    resources: list[Resource], folder: int, *, fallback: int = 0
) -> int | None:
    """Semana donde aparece la carpeta, si ``resources`` la trae."""

    for item in resources:
        if item.kind == FOLDER_TYPE and str(item.resource_id) == str(folder):
            return int(item.session or fallback) or None
    return None


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


def build_plan(
    course: Course,
    target: UploadTarget,
    path: str | Path,
    title: str,
    description: str,
    *,
    param0: str | None = None,
) -> UploadPlan:
    """Valida archivo y textos antes de cualquier peticion de escritura."""

    file, size, warnings = precheck(
        path, target.kind, title=title, description=description, param0=param0
    )
    return UploadPlan(
        target=target,
        course_name=course.name,
        path=file,
        title=title.strip(),
        description=description.strip(),
        param0=(param0 or "").strip(),
        warnings=warnings,
        size_bytes=size,
    )


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #


def register_resource(client: CampusClient, plan: UploadPlan, saved: str) -> UploadResult:
    """Registra el archivo en la carpeta compartida. ``nUAEstado != 1`` = rechazo."""

    data = client.call(
        "Doc_InsertarRecurso",
        {"xml": uploadform.resource_xml(plan, saved)},
        page=uploadform.RESOURCE_PAGE,
        retry_transient=False,
    )
    found = uploadform.records(data, "InsertarRecursos")
    if not found:
        raise CampusError("El campus no devolvio el recurso insertado (InsertarRecursos vacio).")
    record = found[0]
    if uploadform.number(record.get("nUAEstado")) != 1:
        raise CampusError(
            "El campus rechazo el registro en la carpeta "
            f"(nUAEstado={record.get('nUAEstado')!r}): {uploadform.reason(record)}. "
            "El archivo quedo en /Uploads pero no se publico; si el curso lo permite, "
            "proba la misma entrega con --tarea."
        )
    return UploadResult(saved_name=saved, resource_id=record.get("nDocLinNum"))


def register_task(client: CampusClient, plan: UploadPlan, saved: str) -> UploadResult:
    """Registra la entrega en una tarea. Exito: respuesta numerica > 1."""

    data = client.call(
        "Alu_InsertarTarea",
        {"xml": uploadform.task_xml(plan, saved)},
        page=uploadform.TASK_PAGE,
        retry_transient=False,
    )
    value = unwrap(data)
    number = uploadform.number(value)
    if number is None or number <= 1:
        raise CampusError(
            f"El campus rechazo la entrega (respuesta {value!r}). Revisa en el campus "
            "si la tarea ya tiene respuesta, si es sumativa o si cambio de estado."
        )
    return UploadResult(saved_name=saved, task_id=number)


def sync_folder(client: CampusClient, plan: UploadPlan, result: UploadResult) -> str:
    """Avisa a la vista nueva (Mongo) del recurso. Nunca aborta la entrega.

    El cuerpo replica el de ``setCarpetaRecurso`` (``uploadform``); el
    documento Mongo es del campus, asi que un fallo aca solo se avisa: la
    entrega ya quedo registrada. Es una escritura, asi que un 5xx no se
    reintenta: repetirla puede duplicar el documento.
    """

    try:
        student = client.ensure_student_code()
    except CampusError as exc:
        return f"la vista nueva (Mongo) no se sincronizo: {exc}"
    payload = uploadform.folder_sync_payload(
        plan, result, student, timestamp=time.strftime("%d/%m/%Y %H:%M:%S")
    )
    try:
        client.call(
            "setCarpetaRecurso", payload, page=uploadform.TASK_PAGE, retry_transient=False
        )
    except CampusError as exc:
        return f"la vista nueva (Mongo) no se sincronizo: {exc}"
    return ""


# --------------------------------------------------------------------------- #
# Corrida
# --------------------------------------------------------------------------- #


def upload(client: CampusClient, plan: UploadPlan, *, boundary: str | None = None) -> str:
    """Sube el archivo una vez y devuelve el nombre que guardo el campus."""

    boundary = boundary or f"----AutonomaBoundary{uuid.uuid4().hex}"
    try:
        data = plan.path.read_bytes()
    except OSError as exc:
        raise UsageError(f"No se pudo leer el archivo {plan.path}: {exc}") from exc
    body = uploadform.multipart_body(
        data,
        plan.path.name,
        boundary=boundary,
        param0=plan.param0 if plan.target.kind == "tarea" else "",
    )
    raw = client.upload_file(
        body,
        content_type=f"multipart/form-data; boundary={boundary}",
        page=uploadform.UPLOAD_PAGE,
    )
    return uploadform.saved_name(raw)


def deliver(
    client: CampusClient, plan: UploadPlan, *, boundary: str | None = None
) -> UploadResult:
    """Una subida y un registro; el rechazo del campus corta la corrida."""

    saved = upload(client, plan, boundary=boundary)
    if plan.target.kind == "tarea":
        return register_task(client, plan, saved)
    result = register_resource(client, plan, saved)
    result.sync_note = sync_folder(client, plan, result)
    result.synced = not result.sync_note
    return result
