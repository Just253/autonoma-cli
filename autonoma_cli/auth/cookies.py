"""Persistencia de las cookies de sesion del campus.

El jar y su ruta los inyecta quien construye la sesion: este modulo no conoce
la configuracion del usuario.
"""

from __future__ import annotations

import os
from http.cookiejar import Cookie, CookieJar, LoadError
from pathlib import Path


class CookieStore:
    """Lee, guarda y borra el jar; la cookie viva viaja en el mismo jar."""

    def __init__(self, jar: CookieJar, path: str) -> None:
        self.jar = jar
        self.path = path

    def load(self) -> bool:
        """Carga el archivo y dice si quedo alguna cookie sin vencer."""

        try:
            self.jar.load(ignore_discard=True, ignore_expires=False)
        except (OSError, LoadError):
            return False
        return any(not cookie.is_expired() for cookie in self.jar)

    def save(self) -> None:
        """Guarda el jar en disco; si no se puede, la sesion sigue en memoria."""

        try:
            folder = Path(self.path).parent
            folder.mkdir(parents=True, exist_ok=True)
            self.jar.save(ignore_discard=True, ignore_expires=True)
            if os.name != "nt":
                # La carpeta y el archivo se cierran como el resto de la config.
                os.chmod(folder, 0o700)
                os.chmod(self.path, 0o600)
        except (OSError, LoadError):
            pass

    def clear(self) -> bool:
        """Borra el archivo y vacia el jar; True si habia archivo."""

        removed = False
        try:
            if os.path.exists(self.path):
                os.unlink(self.path)
                removed = True
        except OSError:
            pass
        self.jar.clear()
        return removed

    def header(self) -> str:
        """Cabecera ``Cookie`` con las cookies vigentes, ordenada por nombre.

        El orden del jar cambia entre versiones de Python; ordenar deja la
        cabecera y la salida de ``describe`` iguales en todas.
        """

        pairs = [
            f"{cookie.name}={cookie.value}"
            for cookie in self.jar
            if isinstance(cookie, Cookie) and not cookie.is_expired()
        ]
        return "; ".join(sorted(pairs))

    def names(self) -> list[str]:
        """Nombres de las cookies del jar, ordenados."""

        return sorted(cookie.name for cookie in self.jar)
