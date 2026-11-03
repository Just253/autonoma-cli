"""Salida basica: lineas de texto y JSON."""

from __future__ import annotations

import json
import sys
from typing import Any


def text(message: object = "", *, stream: Any = None) -> None:
    """Escribe una linea. Unico punto de salida de texto de los comandos."""

    print(message, file=sys.stdout if stream is None else stream)


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
