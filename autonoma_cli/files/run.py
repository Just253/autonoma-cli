"""Corrida del plan de descarga: serie o hilos, manifiesto y eventos.

La pausa entre pedidos la aplica ``session.send``. Con ``workers > 1`` el
espaciado es aproximado: los hilos comparten la sesion y su marca del ultimo
pedido no esta sincronizada, asi que dos descargas pueden salir juntas.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence
from urllib.request import Request

from ..errors import CampusError, SessionExpiredError
from ..ui import human_size
from .fetch import download_file
from .manifest import Manifest
from .plan import DownloadItem


@dataclass
class DownloadStats:
    """Resultado de una corrida: que se bajo, que ya estaba y que fallo."""

    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    bytes: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def run_plan(
    items: Sequence[DownloadItem],
    manifest: Manifest,
    *,
    send: Callable[..., Any],
    headers: Mapping[str, str],
    workers: int = 1,
    force: bool = False,
    referer: str = "",
    on_event: Callable[[str, DownloadItem, str], None] | None = None,
) -> DownloadStats:
    """Ejecuta el plan. ``on_event`` recibe (tipo, item, detalle).

    En serie el orden es el del plan y la pausa de la sesion se respeta entre
    pedidos. Con ``workers > 1`` las descargas terminan en cualquier orden y el
    espaciado es aproximado, porque los hilos comparten la marca del ultimo
    pedido sin lock.

    En serie, un ``SessionExpiredError`` corta la corrida: con la cookie vencida
    el resto fallaria igual y cada archivo gastaria un pedido al login. Con
    hilos se deja terminar, porque cancelar a mitad deja archivos a medio
    escribir y el resumen mentiria sobre lo que paso.
    """

    stats = DownloadStats()

    def _notify(kind: str, item: DownloadItem, detail: str = "") -> None:
        if on_event:
            on_event(kind, item, detail)

    def _work(item: DownloadItem) -> tuple[str, DownloadItem, int, str]:
        entry = manifest.get(item.resource.url)
        if item.path.exists() and not force:
            known_size = int(entry.get("bytes", 0)) if entry else 0
            current_size = item.path.stat().st_size
            if not entry or not known_size or current_size == known_size:
                return "skip", item, current_size, ""
        size, sha = download_file(
            send,
            item.resource.url,
            item.path,
            headers=headers,
            referer=referer,
        )
        return "done", item, size, sha

    def _record(status: str, item: DownloadItem, size: int, sha: str) -> None:
        if status == "skip":
            stats.skipped += 1
            _notify("skip", item, human_size(size))
            return
        stats.downloaded += 1
        stats.bytes += size
        manifest.put(
            item.resource.url,
            {
                "course": item.course.name,
                "group_id": item.course.group_id,
                "session": item.resource.session,
                "title": item.resource.title,
                "kind": item.resource.kind_name,
                "file": str(item.path),
                "bytes": size,
                "sha256": sha,
                "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        )
        _notify("done", item, human_size(size))

    def _fail(item: DownloadItem, exc: Exception) -> None:
        stats.failed += 1
        stats.failures.append((str(item.path), str(exc)))
        _notify("error", item, str(exc))

    workers = max(1, int(workers))
    if workers == 1 or len(items) == 1:
        for item in items:
            _notify("start", item)
            try:
                status, item, size, sha = _work(item)
            except SessionExpiredError as exc:
                _fail(item, exc)
                break
            except CampusError as exc:
                _fail(item, exc)
                continue
            _record(status, item, size, sha)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_work, item): item for item in items}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    status, item, size, sha = future.result()
                except CampusError as exc:
                    _fail(item, exc)
                    continue
                _record(status, item, size, sha)

    manifest.save()
    return stats
