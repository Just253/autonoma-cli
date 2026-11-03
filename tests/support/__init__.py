"""Piezas compartidas por los tests de la CLI."""

from __future__ import annotations

from .fakes import FakeCampusClient, FakeHistoryClient
from .fixtures import BASE, courses, mixed_courses
from .home import IsolatedHomeMixin

__all__ = [
    "BASE",
    "FakeCampusClient",
    "FakeHistoryClient",
    "IsolatedHomeMixin",
    "courses",
    "mixed_courses",
]
