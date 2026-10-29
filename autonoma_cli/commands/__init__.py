"""Implementacion de los comandos de la CLI.

Cada comando es una funcion ``run_x(client, args) -> int``. El cliente lo
construye ``cli.main`` con :func:`client_for` y se inyecta: ningun comando
instancia ``CampusClient``. Este paquete no importa ``cli`` (evita el ciclo).

Un archivo por tema: ``base`` (lo compartido), ``data`` (cursos y horario con
cache) y un modulo por comando. Este ``__init__`` reexporta la superficie que
usan ``cli.py`` y los tests.
"""

from __future__ import annotations

from .account import run_login, run_logout, run_whoami
from .base import LOGIN_HINT, client_for, out_dir, report_cancelled, report_error
from .courses import run_curso, run_cursos
from .credenciales import run_credenciales
from .data import catalog, schedule
from .download import run_descargar, run_todo
from .maintenance import run_cache
from .resources import run_recursos
from .timetable import run_horario

__all__ = [
    "LOGIN_HINT",
    "catalog",
    "client_for",
    "out_dir",
    "report_cancelled",
    "report_error",
    "run_cache",
    "run_credenciales",
    "run_curso",
    "run_cursos",
    "run_descargar",
    "run_horario",
    "run_login",
    "run_logout",
    "run_recursos",
    "run_todo",
    "run_whoami",
    "schedule",
]
