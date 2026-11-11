"""Destino, plan y resultado de una subida al campus."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class UploadTarget:
    """A donde va la entrega: una carpeta compartida o una tarea del curso."""

    kind: str  # "carpeta" | "tarea"
    number: int  # nDocLinNum del destino (nDocLinGrupo o nDocLinNum de la tarea)
    session: int  # nForoSesion: semana donde vive la carpeta (0 en tareas)
    group_id: int | str  # nGruCodigo / nGruCurso
    course_code: str  # cDocCodigo del curso

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "number": self.number, "session": self.session}


@dataclass(frozen=True)
class UploadPlan:
    """Lo que se va a subir, ya validado y sin haber tocado la red."""

    target: UploadTarget
    course_name: str
    path: Path
    title: str
    description: str
    param0: str = ""
    warnings: tuple[str, ...] = ()
    size_bytes: int = 0

    @property
    def size(self) -> int:
        if self.size_bytes:
            return self.size_bytes
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    @property
    def extension(self) -> str:
        return self.path.suffix.lower().lstrip(".")

    def to_dict(self, *, result: "UploadResult | None" = None) -> dict[str, Any]:
        """Objeto estable de ``--json`` (docs/JSON.md); sin ``result`` es --seco."""

        return {
            "dry_run": result is None,
            "course": {
                "group_id": self.target.group_id,
                "name": self.course_name,
                "code": self.target.course_code,
            },
            "target": self.target.to_dict(),
            "file": {
                "path": str(self.path),
                "name": self.path.name,
                "bytes": self.size,
                "extension": self.extension,
            },
            "title": self.title,
            "description": self.description,
            "param0": self.param0 or None,
            "warnings": list(self.warnings),
            "result": None if result is None else result.to_dict(),
        }


@dataclass
class UploadResult:
    """Lo que contesto el campus despues de registrar la entrega."""

    saved_name: str
    resource_id: int | str | None = None
    task_id: int | None = None
    # None = no se intento (tareas, que no pasan por Mongo); False = fallo.
    synced: bool | None = None
    sync_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "saved_name": self.saved_name,
            "resource_id": self.resource_id,
            "task_id": self.task_id,
            "synced": self.synced,
            "sync_note": self.sync_note,
        }
