"""Rutas, constantes y carpeta de configuracion del usuario.

  Windows  %APPDATA%\\autonoma-cli
  Linux    ~/.config/autonoma-cli
  macOS    ~/.config/autonoma-cli

Se puede cambiar la carpeta con AUTONOMA_CLI_HOME (util para pruebas).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "autonoma-cli"
DEFAULT_BASE_URL = "https://virtual.autonoma.edu.pe"

CREDENTIALS_FILE = "credentials.json"
PLAIN_CREDENTIALS_FILE = "credentials.txt"
COOKIES_FILE = "session.cookies"
SETTINGS_FILE = "settings.json"
CACHE_DIRNAME = "cache"


def home() -> Path:
    """Carpeta de configuracion del usuario, sin crearla."""

    override = os.environ.get("AUTONOMA_CLI_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base).expanduser() if base else Path.home() / ".config"
    return root / APP_NAME


def ensure_home() -> Path:
    """Crea la carpeta de configuracion con permisos cerrados."""

    folder = home()
    folder.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        try:
            folder.chmod(0o700)
        except OSError:
            pass
    return folder


def credentials_path() -> Path:
    return home() / CREDENTIALS_FILE


def plain_credentials_path() -> Path:
    """Archivo de credenciales editable a mano (texto plano)."""

    return home() / PLAIN_CREDENTIALS_FILE


def cookies_path() -> Path:
    return home() / COOKIES_FILE


def settings_path() -> Path:
    return home() / SETTINGS_FILE


def cache_dir() -> Path:
    folder = home() / CACHE_DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder
