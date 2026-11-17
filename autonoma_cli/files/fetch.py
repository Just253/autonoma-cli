"""Descarga de un archivo por el transporte de la sesion.

El pedido lo hace ``send`` (``CampusClient.send``): la sesion aplica la pausa
entre pedidos, el pin de IP y las cookies del jar, y traduce los errores de red
a ``CampusError``. Aca solo se escribe el archivo, se calcula el sha256 y se
decide que error merece otro intento.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request

from ..errors import CampusError, CampusHTTPError, SessionExpiredError

CHUNK = 64 * 1024
# 4xx que si se reintentan: el servidor esta ocupado, no rechaza el pedido.
RETRYABLE_4XX = frozenset({408, 429})
# Una cookie vencida redirige aca; el cuerpo es el formulario, no el archivo.
# Hoy /uploads es publico, asi que esto es una red por si el campus lo protege.
LOGIN_REDIRECT = re.compile(r"/Campus/Login\.aspx(?:$|[?#])", re.I)


def download_file(
    send: Callable[..., Any],
    url: str,
    destination: Path,
    *,
    headers: Mapping[str, str],
    referer: str = "",
    retries: int = 3,
) -> tuple[int, str]:
    """Descarga una URL a ``destination`` de forma atomica.

    Devuelve (bytes, sha256). Reintenta ante error de red o HTTP 5xx; un 4xx
    que no sea 408/429 corta el reintento. El tiempo limite lo aplica el
    transporte de la sesion. Los archivos de ``/uploads`` son publicos, asi que
    el pedido va sin la cookie de sesion.
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
            with send(request, cookies=False) as response, partial.open("wb") as handle:
                if LOGIN_REDIRECT.search(response.geturl()):
                    raise SessionExpiredError("La sesion del campus expiro.")
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
        except SessionExpiredError:
            # Una sesion vencida no se arregla reintentando la misma descarga.
            _discard(partial)
            raise
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
