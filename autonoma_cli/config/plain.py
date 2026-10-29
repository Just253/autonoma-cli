"""Credenciales en texto plano: ``credentials.txt`` editable a mano."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .io import _write_private
from .paths import plain_credentials_path

if TYPE_CHECKING:  # credentials.py ya importa este modulo: sin ciclo en runtime
    from .credentials import Credentials

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

    from .credentials import Credentials

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
