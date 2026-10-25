"""Utilidades de salida: tablas, tamanos y color opcional.

Sin dependencias: se calcula el ancho real de cada columna y se recorta lo que
no entra, para que la salida se lea igual en Windows Terminal y en cualquier
otro terminal.
"""

from __future__ import annotations

import os
import sys
from typing import Iterable, Sequence

_COLOR = False
_CODES = {
    "bold": "1",
    "dim": "2",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "cyan": "36",
}


def configure_color(enabled: bool | None = None) -> bool:
    """Activa o desactiva color. Por defecto: solo si la salida es una TTY."""

    global _COLOR
    if enabled is None:
        enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    _COLOR = bool(enabled)
    return _COLOR


def paint(text: str, code: str) -> str:
    if not _COLOR or code not in _CODES:
        return text
    return f"\x1b[{_CODES[code]}m{text}\x1b[0m"


def bold(text: str) -> str:
    return paint(text, "bold")


def dim(text: str) -> str:
    return paint(text, "dim")


def green(text: str) -> str:
    return paint(text, "green")


def red(text: str) -> str:
    return paint(text, "red")


def yellow(text: str) -> str:
    return paint(text, "yellow")


def cyan(text: str) -> str:
    return paint(text, "cyan")


def truncate(text: str, width: int) -> str:
    text = str(text)
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "\u2026"


def table(
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    *,
    max_widths: Sequence[int] | None = None,
    aligns: Sequence[str] | None = None,
) -> str:
    """Tabla ASCII con columnas alineadas."""

    materialized = [[("" if cell is None else str(cell)) for cell in row] for row in rows]
    columns = len(headers)
    widths = [len(str(header)) for header in headers]
    for row in materialized:
        for index in range(columns):
            cell = row[index] if index < len(row) else ""
            widths[index] = max(widths[index], len(cell))

    if max_widths:
        for index, limit in enumerate(max_widths[:columns]):
            if limit and widths[index] > limit:
                widths[index] = limit

    def render(row: Sequence[str]) -> str:
        cells = []
        for index in range(columns):
            cell = row[index] if index < len(row) else ""
            cell = truncate(cell, widths[index])
            align = aligns[index] if aligns and index < len(aligns) else "left"
            cells.append(cell.rjust(widths[index]) if align == "right" else cell.ljust(widths[index]))
        return "  ".join(cells).rstrip()

    separator = "  ".join("-" * width for width in widths)
    lines = [render([str(header) for header in headers]), separator]
    lines.extend(render(row) for row in materialized)
    return "\n".join(lines)


def header(text: str) -> str:
    return bold(text)


def section(title: str, width: int = 74) -> str:
    return f"\n{bold(title)}\n{'-' * min(width, max(8, len(title)))}"
