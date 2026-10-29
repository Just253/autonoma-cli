"""Escritura de archivos privados (permisos cerrados)."""

from __future__ import annotations

import os
from pathlib import Path


def _write_private(path: Path, payload: str) -> None:
    """Escribe de forma atomica y restringe permisos (no-op en Windows)."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    if os.name != "nt":
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def write_private_text(path: Path, payload: str) -> None:
    """Escribe un archivo con permisos cerrados (usado tambien por la cache)."""

    _write_private(path, payload)
