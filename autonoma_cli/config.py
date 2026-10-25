"""Configuracion local: credenciales, cookies de sesion y preferencias.

Las credenciales se guardan fuera del repositorio, en el directorio de
configuracion del usuario:

  Windows  %APPDATA%\\autonoma-cli
  Linux    ~/.config/autonoma-cli
  macOS    ~/.config/autonoma-cli

En Windows el secreto se cifra con DPAPI (CryptProtectData): solo la misma
cuenta de Windows puede descifrarlo. En otras plataformas se guarda en claro
con permisos 0600 y se avisa al usuario.

Se puede cambiar la carpeta con AUTONOMA_CLI_HOME (util para pruebas).
"""

from __future__ import annotations

import base64
import binascii
import ctypes
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # ctypes.wintypes solo existe en Windows
    from ctypes import wintypes
except ImportError:  # pragma: no cover - plataformas sin wintypes
    wintypes = None  # type: ignore[assignment]

APP_NAME = "autonoma-cli"
DEFAULT_BASE_URL = "https://virtual.autonoma.edu.pe"

CREDENTIALS_FILE = "credentials.json"
PLAIN_CREDENTIALS_FILE = "credentials.txt"
COOKIES_FILE = "session.cookies"
SETTINGS_FILE = "settings.json"
CACHE_DIRNAME = "cache"


# --------------------------------------------------------------------------- #
# Rutas
# --------------------------------------------------------------------------- #


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


# --------------------------------------------------------------------------- #
# Cifrado con DPAPI (solo Windows)
# --------------------------------------------------------------------------- #

CRYPTPROTECT_UI_FORBIDDEN = 0x01

if wintypes is not None:

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _protect(data: bytes) -> bytes:
    """Cifra con DPAPI. Solo disponible en Windows."""

    if os.name != "nt":
        raise OSError("DPAPI solo existe en Windows")
    blob_in = _blob(data)
    blob_out = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "autonoma-cli",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptProtectData fallo")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    """Descifra con DPAPI. Solo disponible en Windows."""

    if os.name != "nt":
        raise OSError("DPAPI solo existe en Windows")
    blob_in = _blob(data)
    blob_out = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptUnprotectData fallo")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


# --------------------------------------------------------------------------- #
# Credenciales
# --------------------------------------------------------------------------- #


METHOD_LABELS = {
    "dpapi": "cifradas con DPAPI (solo tu usuario de Windows)",
    "plain": "guardadas sin cifrar",
    "plain_file": "en credentials.txt (texto plano, editable a mano)",
    "env": "en variables de entorno",
}


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str
    method: str  # dpapi | plain | env

    @property
    def storage_label(self) -> str:
        return METHOD_LABELS.get(self.method, self.method)


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


PLAIN_CREDENTIALS_TEMPLATE = """# Credenciales del Campus Virtual - autonoma-cli
#
# Edita estas dos lineas, guarda el archivo y listo: la CLI lo lee en cada
# comando. Este archivo tiene PRIORIDAD sobre las credenciales cifradas que
# guarda `autonoma login`.
#
# Ojo: esta en texto plano. No lo compartas, no lo subas a un repo y, si
# quieres volver al cifrado, borralo y ejecuta `autonoma login`.
#
# Acepta tambien: user= / username= / clave= / contrasena=

usuario=
password=
"""

_KEY_ALIASES = {
    "usuario": "username",
    "user": "username",
    "username": "username",
    "correo": "username",
    "password": "password",
    "pass": "password",
    "clave": "password",
    "contrasena": "password",
    "contraseña": "password",
}


def _parse_plain_credentials(path: Path) -> Credentials | None:
    """Lee ``usuario=`` / ``password=`` de un archivo de texto."""

    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None

    values: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        separator = "=" if "=" in line else ":" if ":" in line else ""
        if not separator:
            continue
        key, _, value = line.partition(separator)
        field_name = _KEY_ALIASES.get(key.strip().lower())
        if not field_name:
            continue
        value = value.strip().strip('"').strip("'")
        if value:
            values[field_name] = value

    username = values.get("username", "")
    password = values.get("password", "")
    if not username or not password:
        return None
    return Credentials(username=username, password=password, method="plain_file")


def create_plain_credentials_file() -> tuple[Path, bool]:
    """Crea ``credentials.txt`` con la plantilla si no existe.

    Devuelve (ruta, creado). Nunca sobrescribe un archivo existente.
    """

    path = plain_credentials_path()
    if path.exists():
        return path, False
    _write_private(path, PLAIN_CREDENTIALS_TEMPLATE)
    return path, True


def read_plain_credentials() -> Credentials | None:
    path = plain_credentials_path()
    if not path.exists():
        return None
    return _parse_plain_credentials(path)


def clear_plain_credentials() -> bool:
    path = plain_credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


def save_credentials(username: str, password: str) -> Credentials:
    """Guarda usuario y contrasena para no volver a escribirlos."""

    username = username.strip()
    if not username or not password:
        raise ValueError("Usuario y contrasena son obligatorios")

    secret = json.dumps({"username": username, "password": password}).encode("utf-8")
    document: dict[str, Any] = {
        "version": 1,
        "app": APP_NAME,
        "username": username,
    }
    try:
        document["method"] = "dpapi"
        document["blob"] = base64.b64encode(_protect(secret)).decode("ascii")
        method = "dpapi"
    except Exception:  # DPAPI ausente o bloqueado
        document["method"] = "plain"
        document["blob"] = base64.b64encode(secret).decode("ascii")
        method = "plain"

    _write_private(credentials_path(), json.dumps(document, indent=2))
    if method == "plain":
        location = "con permisos 0600" if os.name != "nt" else "sin cifrar"
        print(
            f"aviso: la contrasena quedo guardada {location} en {credentials_path()}",
            file=sys.stderr,
        )
    return Credentials(username=username, password=password, method=method)


def load_credentials() -> Credentials | None:
    """Devuelve las credenciales guardadas o las de las variables de entorno."""

    env_user = os.environ.get("AUTONOMA_USER")
    env_password = os.environ.get("AUTONOMA_PASSWORD")
    if env_user and env_password:
        return Credentials(username=env_user, password=env_password, method="env")

    editable = read_plain_credentials()
    if editable is not None:
        return editable

    path = credentials_path()
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        blob = base64.b64decode(document.get("blob", ""))
        method = str(document.get("method", "plain"))
        if method == "dpapi":
            payload = _unprotect(blob)
        else:
            payload = blob
        data = json.loads(payload.decode("utf-8"))
        username = str(data.get("username") or document.get("username") or "")
        password = str(data.get("password") or "")
        if not username or not password:
            return None
        return Credentials(username=username, password=password, method=method)
    except (OSError, ValueError, binascii.Error, json.JSONDecodeError):
        # Archivo corrupto, de otro usuario de Windows o de otra maquina.
        return None


def clear_credentials() -> bool:
    path = credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


def credentials_info() -> dict[str, Any] | None:
    """Metadatos de las credenciales guardadas (nunca la contrasena)."""

    plain = plain_credentials_path()
    if plain.exists():
        editable = read_plain_credentials()
        return {
            "path": str(plain),
            "username": editable.username if editable else "",
            "method": "plain_file",
            "label": METHOD_LABELS["plain_file"],
            "complete": editable is not None,
            "exists": True,
        }

    path = credentials_path()
    if not path.exists() and not (
        os.environ.get("AUTONOMA_USER") and os.environ.get("AUTONOMA_PASSWORD")
    ):
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        document = {}
    method = "env" if os.environ.get("AUTONOMA_USER") else str(document.get("method", "plain"))
    return {
        "path": str(path),
        "username": document.get("username") or os.environ.get("AUTONOMA_USER", ""),
        "method": method,
        "label": METHOD_LABELS.get(method, method),
        "complete": True,
        "exists": True,
    }


# --------------------------------------------------------------------------- #
# Preferencias
# --------------------------------------------------------------------------- #


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
