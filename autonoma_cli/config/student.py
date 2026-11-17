"""Codigo de alumno guardado entre corridas.

El panel no siempre lo trae: con la cookie guardada no hay login y
``Default.aspx`` no repite el codigo, asi que el historial y las claves de
cache quedan sin identidad. Se guarda junto a la cookie para no pedir el panel
en cada corrida.
"""

from __future__ import annotations

import json
from pathlib import Path

from .io import write_private
from .paths import home

STUDENT_FILE = "student.json"


def student_path() -> Path:
    """Archivo con el codigo de alumno de la ultima sesion."""

    return home() / STUDENT_FILE


def load_student_code(path: Path | None = None) -> str:
    """Codigo guardado; un archivo ausente o roto devuelve cadena vacia."""

    target = Path(path) if path is not None else student_path()
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(document, dict):
        return ""
    return str(document.get("code") or "").strip()


def save_student_code(code: str, path: Path | None = None) -> None:
    """Guarda el codigo con permisos cerrados; vacio borra el archivo."""

    target = Path(path) if path is not None else student_path()
    value = (code or "").strip()
    if not value:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        return
    write_private(target, json.dumps({"code": value}, ensure_ascii=False))


class StudentCode:
    """El archivo del codigo de alumno, atado a una ruta concreta."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else student_path()

    def load(self) -> str:
        return load_student_code(self.path)

    def save(self, code: str) -> None:
        save_student_code(code, self.path)
