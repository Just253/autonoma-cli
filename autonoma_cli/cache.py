"""Cache local de respuestas del campus en un unico documento JSON.

Documento::

    {"version": 1, "base_url": "...", "entries": {"clave": {"at": 1.0, "value": ...}}}

Reglas:

  - Archivo ausente, JSON corrupto, otra ``version`` o un ``base_url`` distinto
    dan un documento vacio: nunca una excepcion.
  - La frescura es estricta (``ahora - at < ttl``): justo en el limite la
    entrada ya se considera vencida.
  - ``None`` es la unica marca de miss. Una lista vacia es un valor valido y se
    cachea: antes ``items`` vacia forzaba un refetch en cada comando, ahora se
    respeta lo que devolvio el campus.
  - ``save`` escribe de forma atomica y con permisos cerrados
    (``config.write_private_text``) y, como mejor esfuerzo, borra los
    ``cursos.json`` / ``horario.json`` de la version anterior.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from . import config

VERSION = 1
CACHE_FILE = "cache.json"
LEGACY_FILES = ("cursos.json", "horario.json")

MAX_AGE_CURSOS = 6 * 3600
MAX_AGE_HORARIO = 6 * 3600
# Una hora: el docente sube material durante la semana, pero no cada minuto.
MAX_AGE_RECURSOS = 3600


class Cache:
    """Documento de cache de un campus concreto."""

    def __init__(self, path: Path, base_url: str) -> None:
        self.path = Path(path)
        self.base_url = base_url
        self.entries: dict[str, Any] = {}
        self.loaded = False

    def load(self) -> None:
        """Lee el documento. Cualquier problema deja la cache vacia."""
        self.loaded = True
        self.entries = {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(document, dict) or document.get("version") != VERSION:
            return
        if document.get("base_url") != self.base_url:
            return
        entries = document.get("entries")
        if isinstance(entries, dict):
            self.entries = {str(k): v for k, v in entries.items() if isinstance(v, dict)}

    def get(self, key: str, ttl: float, now: float | None = None) -> Any:
        record = self.entries.get(key)
        if not isinstance(record, dict) or "value" not in record:
            return None
        try:
            stamp = float(record.get("at"))
        except (TypeError, ValueError):
            return None
        current = time.time() if now is None else now
        return record["value"] if current - stamp < ttl else None

    def set(self, key: str, value: Any, now: float | None = None) -> None:
        self.entries[key] = {"at": time.time() if now is None else now, "value": value}

    def save(self) -> None:
        document = {"version": VERSION, "base_url": self.base_url, "entries": self.entries}
        try:
            config.write_private_text(self.path, json.dumps(document, ensure_ascii=False))
            for name in LEGACY_FILES:  # documentos de la version anterior
                (self.path.parent / name).unlink(missing_ok=True)
        except OSError:
            pass

    def clear(self) -> None:
        self.entries = {}
        self.loaded = True
        try:
            self.path.unlink()
        except OSError:
            pass


def for_campus(base_url: str) -> Cache:
    """Cache del campus dentro de la carpeta de configuracion del usuario."""
    return Cache(config.cache_dir() / CACHE_FILE, base_url)


def ensure(
    cache: Cache,
    key: str,
    *,
    ttl: float,
    fetch: Callable[[], Any],
    force: bool = False,
) -> Any:
    """Unica forma de traer datos con cache: fresco o ``fetch()`` + guardar."""
    if not cache.loaded:
        cache.load()
    if not force:
        cached = cache.get(key, ttl)
        if cached is not None:
            return cached
    value = fetch()
    cache.set(key, value)
    cache.save()
    return value


def ensure_pairs(
    cache: Cache,
    key: str,
    *,
    ttl: float,
    fetch: Callable[[], Any],
    force: bool = False,
) -> list[tuple[int, list[dict[str, Any]]]]:
    """Como ``ensure`` pero solo acepta ``[[numero, [registros]], ...]``.

    Un valor de otra version o a medio escribir se descarta y se vuelve a
    pedir: es como se cachean los datos que van por sesion sin arrastrar
    basura a los comandos.
    """

    pairs = _pairs(ensure(cache, key, ttl=ttl, fetch=fetch, force=force))
    if pairs is None:
        pairs = _pairs(ensure(cache, key, ttl=ttl, fetch=fetch, force=True)) or []
    return pairs


def _student_key(student: str, name: str, suffix: str) -> str:
    return f"{name}:{student}:{suffix}" if suffix else f"{name}:{student}"


def ensure_for(
    base_url: str,
    student: str,
    name: str,
    *,
    ttl: float,
    fetch: Callable[[], Any],
    refresh: bool = False,
    suffix: str = "",
) -> Any:
    """Como ``ensure`` pero por alumno; sin identidad no cachea.

    Dos cuentas en la misma carpeta no pueden compartir una entrada, y una
    sesion sin codigo no tiene con que distinguirse.
    """

    if not student:
        return fetch()
    return ensure(
        for_campus(base_url),
        _student_key(student, name, suffix),
        ttl=ttl,
        fetch=fetch,
        force=refresh,
    )


def ensure_pairs_for(
    base_url: str,
    student: str,
    name: str,
    *,
    ttl: float,
    fetch: Callable[[], Any],
    refresh: bool = False,
    suffix: str = "",
) -> list[tuple[int, list[dict[str, Any]]]]:
    """Como ``ensure_pairs`` pero por alumno; sin identidad no cachea."""

    if not student:
        return _pairs(fetch()) or []
    return ensure_pairs(
        for_campus(base_url),
        _student_key(student, name, suffix),
        ttl=ttl,
        fetch=fetch,
        force=refresh,
    )


def _pairs(value: Any) -> list[tuple[int, list[dict[str, Any]]]] | None:
    """Pares (numero, registros) de un valor guardado; ``None`` si no sirve.

    Un par a medio escribir invalida el documento entero: es preferible volver
    a pedir que arrastrar una lista recortada a los comandos.
    """

    if not isinstance(value, list):
        return None
    pairs: list[tuple[int, list[dict[str, Any]]]] = []
    for entry in value:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            return None
        number, items = entry
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            return None
        try:
            pairs.append((int(number), items))
        except (TypeError, ValueError):
            return None
    return pairs
