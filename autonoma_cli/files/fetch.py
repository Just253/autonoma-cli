"""Descarga de un archivo por el transporte de la sesion.

El pedido lo hace ``send`` (``CampusClient.send``): la sesion aplica la pausa
entre pedidos, el pin de IP y las cookies del jar, y traduce los errores de red
a ``CampusError``. Aca solo se escribe el archivo, se calcula el sha256 y se
decide que error merece otro intento.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request

from ..errors import CampusError, CampusHTTPError

CHUNK = 64 * 1024
# 4xx que si se reintentan: el servidor esta ocupado, no rechaza el pedido.
RETRYABLE_4XX = frozenset({408, 429})


def download_file(
    send: Callable[[Request], Any],
    url: str,
    destination: Path,
    *,
    headers: Mapping[str, str],
    referer: str = "",
    timeout: float = 60.0,
    retries: int = 3,
) -> tuple[int, str]:
    """Descarga una URL a ``destination`` de forma atomica.

    Devuelve (bytes, sha256). Reintenta ante error de red o HTTP 5xx; un 4xx
    que no sea 408/429 corta el reintento. El tiempo limite lo aplica el
    transporte de la sesion: ``timeout`` se acepta para que la corrida fije uno
    solo y no haya dos relojes en juego.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    request_headers = {**headers, "Accept": "*/*"}
    if referer:
        request_headers["Referer"] = referer

    last_error: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            request = Request(url, headers=request_headers)
            digest = hashlib.sha256()
            size = 0
            with send(request) as response, partial.open("wb") as handle:
                while True:
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            if size == 0:
                raise CampusError("El archivo llego vacio.")
            os.replace(partial, destination)
            return size, digest.hexdigest()
        except CampusHTTPError as exc:
            last_error = exc
            _discard(partial)
            if 400 <= exc.status_code < 500 and exc.status_code not in RETRYABLE_4XX:
                break
        except (CampusError, OSError) as exc:
            last_error = exc
            _discard(partial)
        if attempt < retries:
            time.sleep(1.5 * attempt)
    raise CampusError(f"No se pudo descargar {url}: {last_error}")


def _discard(partial: Path) -> None:
    """Borra el ``.part`` de un intento fallido; si no se puede, se ignora."""

    try:
        if partial.exists():
            partial.unlink()
    except OSError:
        pass
