"""Desempaquetado de las respuestas del campus.

El campus contesta ``{"d": ...}`` y a veces mete el JSON como string dentro de
``d``; las subidas, ademas, pueden devolver el texto pelado.
"""

from __future__ import annotations

import json
from typing import Any, Mapping


def unwrap(payload: Any) -> Any:
    """Desenvuelve ``{"d": ...}``, incluso cuando ``d`` es un string JSON."""

    if not isinstance(payload, Mapping) or "d" not in payload:
        return payload
    value = payload["d"]
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def parse_json_text(raw: str) -> Any:
    """Devuelve el JSON que trae ``raw`` y lo desenvuelve; si no es JSON, el texto.

    Lo usan las subidas: ``FileUpload.ashx`` contesta el nombre guardado como
    texto pelado, pero algunas versiones lo mandan como ``{"d": ...}``.
    """

    try:
        return unwrap(json.loads(raw))
    except (TypeError, ValueError):
        return raw


def records(data: Any) -> list[Mapping[str, Any]]:
    """Filas de una respuesta que puede venir anidada bajo una clave conocida."""

    data = unwrap(data)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping):
        for key in ("recursos", "items", "data", "result"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, Mapping)]
    return []
