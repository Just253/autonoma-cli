"""Filas de recursos para la tabla de ``ui``."""

from __future__ import annotations

from typing import Sequence

from ..models import Resource


def resource_rows(resources: Sequence[Resource]) -> list[list[str]]:
    return [
        [
            resource.session_label,
            resource.kind_name,
            resource.title[:60],
            resource.extension.lstrip(".") or "-",
            resource.date,
        ]
        for resource in resources
    ]
