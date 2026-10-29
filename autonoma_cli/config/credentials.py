"""Credenciales: cifrado con DPAPI o guardado en claro, y su lectura."""

from __future__ import annotations

import base64
import binascii
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from .crypto import _protect, _unprotect
from .io import _write_private
from .paths import APP_NAME, credentials_path, plain_credentials_path
from .plain import read_plain_credentials

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
