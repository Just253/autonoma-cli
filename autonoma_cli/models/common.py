"""Normalizacion compartida: texto, numeros, fechas y nombres de archivo.

La API interna devuelve campos con formatos mezclados (HTML, fechas en varios
ordenes, numeros como texto). Estos helpers son la base del resto del paquete:
ningun otro submodulo define su propia version.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SPACES = re.compile(r"\s+")

_ACCENTS = str.maketrans("áéíóúÁÉÍÓÚñÑüÜ", "aeiouAEIOUnNuU")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fold(text: Any) -> str:
    """Minusculas y sin acentos: comparar texto del campus sin pelearse."""

    return clean_text(text).translate(_ACCENTS).casefold()


_TAGS = re.compile(r"<[^>]+>")


def strip_html(value: Any) -> str:
    """Quita etiquetas y espacios sobrantes (el campus manda HTML en ``tipo``)."""

    return re.sub(r"\s+", " ", _TAGS.sub(" ", clean_text(value))).strip()


_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d")


def parse_date(value: Any) -> date | None:
    """Interpreta ``dd/mm/aaaa``, ``dd-mm-aaaa`` o ``aaaa-mm-dd``."""

    text = clean_text(value)
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_float(value: Any) -> float | None:
    """Numero decimal del campus; vacio, ``"-"`` o basura devuelven None.

    Las notas llegan como texto con punto decimal (``"12.50"``) o como ``"-"``
    cuando el criterio todavia no esta calificado.
    """

    text = clean_text(value)
    if not text or text in {"-", "--"}:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    """Entero a partir del mismo texto tolerante de :func:`parse_float`."""

    number = parse_float(value)
    return int(number) if number is not None else None


def date_from_millis(value: Any) -> date | None:
    """Respaldo de ``fechaParse``: milisegundos desde epoch, en UTC."""

    try:
        millis = float(value)
    except (TypeError, ValueError):
        return None
    if millis <= 0:
        return None
    try:
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date()
    except (OverflowError, OSError, ValueError):
        return None


def slugify(text: str, *, limit: int = 70) -> str:
    """Convierte un titulo en un nombre seguro para archivos y carpetas."""

    text = clean_text(text).translate(_ACCENTS)
    text = _INVALID_FILENAME.sub("", text)
    text = re.sub(r"[^\w.\-]+", "_", text)
    text = _SPACES.sub("_", text)
    text = re.sub(r"_+", "_", text).strip("._-")
    return text[:limit].strip("._-") or "sin_titulo"


def safe_filename(text: str, *, fallback: str = "archivo", limit: int = 90) -> str:
    text = clean_text(text).translate(_ACCENTS)
    text = _INVALID_FILENAME.sub("", text)
    text = _SPACES.sub(" ", text).strip(" .")
    if not text:
        return fallback
    stem, extension = os.path.splitext(text)
    if len(text) > limit:
        text = stem[: max(1, limit - len(extension))].rstrip(" ._") + extension
    return text or fallback


def resolve_upload_url(base_url: str, url: Any) -> str:
    """Resuelve la URL real de un recurso.

    La API entrega tres formas:
      - nombre relativo a /uploads/  (``01-03-2027_..._DOCUMENTO.pdf``)
      - ruta absoluta al dominio     (``/UploadsEnvioEmailPDF/...pdf``)
      - URL completa                 (``https://...``)
    Algunos campos traen sufijos separados por ``||`` que hay que descartar.
    """

    text = clean_text(url).split("||")[0].strip()
    if not text:
        return ""
    if text.lower().startswith(("http://", "https://")):
        return text
    if text.startswith("/"):
        return urljoin(base_url.rstrip("/") + "/", text.lstrip("/"))
    return f"{base_url.rstrip('/')}/uploads/{quote(text, safe='/')}"
