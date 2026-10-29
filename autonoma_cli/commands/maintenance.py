"""Comando `cache`: ver o borrar la cache local."""

from __future__ import annotations

import argparse

from .. import config, render
from ..client import CampusClient
from ..downloader import human_size


def run_cache(client: CampusClient | None, args: argparse.Namespace) -> int:
    folder = config.cache_dir()
    files = sorted(folder.glob("*.json"))
    if args.borrar:
        removed = 0
        for file in files:
            try:
                file.unlink()
                removed += 1
            except OSError:
                pass
        render.text(f"Cache borrada: {removed} archivos en {folder}")
        return 0
    if args.json:
        render.emit_json({"dir": str(folder), "files": [file.name for file in files]})
        return 0
    render.text(f"Cache: {folder}")
    if not files:
        render.text("  (vacia)")
    for file in files:
        render.text(f"  {file.name} · {human_size(file.stat().st_size)}")
    return 0
