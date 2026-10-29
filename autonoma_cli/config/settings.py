"""Preferencias: settings.json y variables de entorno."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io import _write_private
from .paths import DEFAULT_BASE_URL, settings_path


@dataclass(frozen=True)
class Settings:
    base_url: str = DEFAULT_BASE_URL
    timeout: float = 30.0
    delay: float = 0.5
    workers: int = 4
    out_dir: str = "descargas"
    max_sessions: int = 20


_ENV_KEYS = {
    "AUTONOMA_BASE_URL": ("base_url", str),
    "AUTONOMA_TIMEOUT": ("timeout", float),
    "AUTONOMA_DELAY": ("delay", float),
    "AUTONOMA_WORKERS": ("workers", int),
    "AUTONOMA_OUT": ("out_dir", str),
}


def load_settings() -> Settings:
    """Precedencia: opciones de la CLI > variables de entorno > settings.json."""

    data: dict[str, Any] = {}
    path = settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}

    values: dict[str, Any] = {}
    for field_name in ("base_url", "timeout", "delay", "workers", "out_dir", "max_sessions"):
        if field_name in data:
            values[field_name] = data[field_name]

    for env_key, (field_name, cast) in _ENV_KEYS.items():
        raw = os.environ.get(env_key)
        if raw:
            try:
                values[field_name] = cast(raw)
            except ValueError:
                pass

    try:
        return Settings(**values)
    except TypeError:
        return Settings()


def save_settings(*, timeout: float | None = None, delay: float | None = None,
                  workers: int | None = None, out_dir: str | None = None) -> Path:
    """Persiste las preferencias indicadas, conservando el resto."""

    current = load_settings()
    document = {
        "base_url": current.base_url,
        "timeout": current.timeout if timeout is None else timeout,
        "delay": current.delay if delay is None else delay,
        "workers": current.workers if workers is None else workers,
        "out_dir": current.out_dir if out_dir is None else out_dir,
        "max_sessions": current.max_sessions,
    }
    _write_private(settings_path(), json.dumps(document, indent=2))
    return settings_path()
