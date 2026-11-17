"""Manifiesto de descargas: ``manifest.json`` en la raiz de la carpeta destino.

Guarda URL -> archivo, bytes y sha256 para no volver a bajar lo mismo y para
poder verificar despues lo que ya esta en disco. La escritura es atomica: se
escribe ``.tmp`` y se renombra, asi una corrida cortada no deja el manifiesto a
medias.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

MANIFEST_NAME = "manifest.json"


class Manifest:
    """Registro de descargas: URL -> archivo, bytes y sha256."""

    def __init__(self, root: Path) -> None:
        self.path = root / MANIFEST_NAME
        self.entries: dict[str, dict[str, Any]] = {}
        self.dirty = False
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            entries = document.get("entries")
            if isinstance(entries, dict):
                self.entries = {str(key): value for key, value in entries.items()}
        except (OSError, json.JSONDecodeError):
            self.entries = {}

    def get(self, url: str) -> dict[str, Any] | None:
        return self.entries.get(url)

    def put(self, url: str, entry: Mapping[str, Any]) -> None:
        self.entries[url] = dict(entry)
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": 1, "entries": self.entries},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)
        self.dirty = False
