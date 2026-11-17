"""Validacion de la entrega antes de gastar peticiones.

Vive aparte de ``uploader.py`` para que el comando pueda validar archivo y
textos antes de pedir el catalogo del curso, sin arrastrar la corrida. Es el
unico modulo que decide si un archivo sirve para ``--carpeta`` o ``--tarea``.
"""

from __future__ import annotations

from pathlib import Path

from .errors import UsageError
from .ui import human_size

MAX_BYTES = 25 * 1024 * 1024
WARN_BYTES = 5 * 1024 * 1024
FOLDER_EXTENSIONS = ("pdf", "rar", "zip")


def precheck(
    path: str | Path,
    kind: str,
    *,
    title: str,
    description: str,
    param0: str | None = None,
) -> tuple[Path, int, tuple[str, ...]]:
    """Valida textos y archivo sin tocar la red ni resolver el curso.

    ``commands/entregar.py`` la llama antes de pedir el catalogo: un archivo que
    no existe o un ``--param0`` con ``--carpeta`` no gastan ni una peticion.
    """

    title = (title or "").strip()
    description = (description or "").strip()
    param0 = (param0 or "").strip()
    if not title:
        raise UsageError("--titulo es obligatorio: es el nombre visible del recurso.")
    if not description:
        raise UsageError("--descripcion es obligatoria: el campus la pide al registrar.")
    if kind != "tarea" and param0:
        raise UsageError("--param0 solo vale con --tarea: en carpetas se conserva el nombre.")

    file = Path(path).expanduser()
    if not file.is_file():
        raise UsageError(f"No existe el archivo: {file}")
    try:
        size = file.stat().st_size
    except OSError as exc:
        raise UsageError(f"No se pudo leer el archivo {file}: {exc}") from exc
    if size == 0:
        raise UsageError(f"El archivo esta vacio: {file}")

    extension = file.suffix.lower().lstrip(".")
    warnings: list[str] = []
    if kind == "carpeta":
        if extension not in FOLDER_EXTENSIONS:
            allowed = ", ".join(f".{item}" for item in FOLDER_EXTENSIONS)
            raise UsageError(
                f"Una carpeta compartida solo acepta {allowed}; {file.name} no sirve. "
                "Si es para una tarea, usa --tarea."
            )
        if size > WARN_BYTES:
            warnings.append(
                f"{human_size(size)}: el widget de carpeta dice 5 MB, pero el servidor "
                "acepto mas; se sube igual."
            )
    if size > MAX_BYTES:
        raise UsageError(
            f"{file.name} pesa {human_size(size)} y el maximo es {human_size(MAX_BYTES)}."
        )
    return file, size, tuple(warnings)
