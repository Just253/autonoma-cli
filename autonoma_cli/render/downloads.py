"""Progreso y resumen de una descarga."""

from __future__ import annotations

import sys
from typing import Any

from .. import ui
from ..downloader import DownloadItem, human_size


def progress(kind: str, item: DownloadItem, detail: str) -> None:
    label = f"S{int(item.resource.session):02d} · {item.resource.title[:64]}"
    if kind == "done":
        print(f"  {ui.green('[ok]')}   {label} ({detail})")
    elif kind == "skip":
        print(f"  {ui.dim('[igual]')} {label}")
    elif kind == "error":
        print(f"  {ui.red('[error]')} {label}: {detail}", file=sys.stderr)


def print_stats(stats: Any, dry_run: bool = False) -> None:
    if dry_run:
        return
    print()
    print(
        f"Descargados: {stats.downloaded} · Ya estaban: {stats.skipped} · "
        f"Errores: {stats.failed} · Total: {human_size(stats.bytes)}"
    )
    for path, message in stats.failures:
        print(f"  {ui.red('x')} {path}: {message}", file=sys.stderr)
