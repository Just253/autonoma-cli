"""Piezas compartidas por los tests de la CLI."""

from __future__ import annotations

from .fakes import FakeCampusClient, FakeHistoryClient
from .fixtures import BASE, courses, mixed_courses
from .home import IsolatedHomeMixin
from .uploads import FOLDER, SESSION, TASK, UploadClient, folder_resource

__all__ = [
    "BASE",
    "FakeCampusClient",
    "FakeHistoryClient",
    "FOLDER",
    "IsolatedHomeMixin",
    "SESSION",
    "TASK",
    "UploadClient",
    "courses",
    "folder_resource",
    "mixed_courses",
]
