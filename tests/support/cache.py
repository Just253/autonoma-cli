"""Piezas compartidas por los tests de cache."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autonoma_cli import cache, config
from autonoma_cli.models import ClassSession, Course

BASE = "https://virtual.autonoma.edu.pe"
OTHER = "https://otro.example.edu.pe"
NOW = 1_800_000_000.0
STUDENT = "20240001"
COURSES_KEY = f"cursos:{STUDENT}"


def raw_course(group_id: int, name: str) -> dict:
    return {"nGruCodigo": group_id, "asignatura": name, "codigo": f"COD{group_id}"}


def raw_schedule(topic: str) -> dict:
    return {
        "fecha": "20/10/2026 08:00 a 10:00",
        "asignatura": "CURSO DE EJEMPLO",
        "nSesion": 1,
        "cSesion": "01",
        "tema": topic,
    }


def entry(at: float, value: object) -> dict:
    return {"at": at, "value": value}


def document(entries: dict, *, base_url: str = BASE) -> dict:
    return {"version": cache.VERSION, "base_url": base_url, "entries": entries}


def cache_path() -> Path:
    return config.cache_dir() / cache.CACHE_FILE


class FakeClient:
    """Cliente de mentira: cuenta llamadas y no toca la red."""

    def __init__(self, *, base_url: str = BASE) -> None:
        self.base_url = base_url
        self.student_code = STUDENT
        self.course_calls = 0
        self.schedule_calls: list[object] = []

    def get_courses(self) -> list[Course]:
        self.course_calls += 1
        return [Course.from_api(raw_course(90000001, "CURSO FRESCO"), self.base_url)]

    def get_schedule(self, group_id: object, *, course: str = "") -> list[ClassSession]:
        self.schedule_calls.append(group_id)
        data = raw_schedule("Tema fresco")
        data["nGruCodigo"] = group_id
        data["asignatura"] = course or data["asignatura"]
        return [ClassSession.from_api(data, group_id=group_id, course=course)]

    def get_syllabus(self, group_id: object) -> list:
        return []

    def get_course_detail(self, group_id: object, session: int) -> dict:
        return {}

    def iter_session_resources(self, group_id: object) -> list:
        return []


class CacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.dict(os.environ, {"AUTONOMA_CLI_HOME": self._tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, payload: dict) -> Path:
        path = cache_path()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    @staticmethod
    def read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def course(self, group_id: int, name: str) -> Course:
        return Course.from_api(raw_course(group_id, name), BASE)
