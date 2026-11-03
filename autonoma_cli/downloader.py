"""Planificacion y descarga de archivos del campus.

- Estructura destino: ``<out>/<curso>/Sesion_NN/<TIPO>_<titulo>.<ext>``
- Descarga atomica: escribe ``.part`` y renombra al terminar.
- Manifiesto ``manifest.json`` en la raiz de descargas: evita volver a bajar
  lo mismo y deja el sha256 de cada archivo.
- Hilos: cada descarga usa la cookie de la sesion, sin compartir el opener.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .client import _cert_mismatch, _flush_dns
from .errors import CampusError
from .models import Course, Resource, kind_tag, safe_filename, slugify

MANIFEST_NAME = "manifest.json"
CHUNK = 64 * 1024


# --------------------------------------------------------------------------- #
# Manifiesto
# --------------------------------------------------------------------------- #


class Manifest:
    """Registro de descargas: URL -> archivo, bytes y sha256."""

    def __init__(self, root: Path) -> None:
        self.path = root / MANIFEST_NAME
        self.entries: dict[str, dict[str, Any]] = {}
        self.dirty = False
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
            entries = document.get("entries")
            if isinstance(entries, dict):
                self.entries = {str(key): value for key, value in entries.items()}
        except (OSError, json.JSONDecodeError):
            self.entries = {}

    def get(self, url: str) -> dict[str, Any] | None:
        return self.entries.get(url)

    def put(self, url: str, entry: Mapping[str, Any]) -> None:
        self.entries[url] = dict(entry)
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": 1, "entries": self.entries},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self.path)
        self.dirty = False


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


@dataclass
class DownloadItem:
    course: Course
    resource: Resource
    path: Path

    @property
    def label(self) -> str:
        return f"Sesion {self.resource.session_label} · {self.resource.title}"


def course_folder(course: Course) -> str:
    return slugify(f"{course.name}", limit=60) or f"curso_{course.group_id}"


def build_filename(resource: Resource) -> str:
    extension = resource.extension or ".bin"
    tag = kind_tag(resource.kind)
    title = slugify(resource.title, limit=80)
    return f"{tag}_{title}{extension}"


def plan_course(
    course: Course,
    sessions: Sequence[tuple[int, list[Resource]]],
    out_root: Path,
    *,
    kinds: set[int] | None = None,
    only: re.Pattern[str] | None = None,
    include_syllabus: bool = False,
) -> list[DownloadItem]:
    """Convierte (sesion, recursos) en rutas destino sin repetir nombres."""

    base = out_root / course_folder(course)
    items: list[DownloadItem] = []
    used: set[Path] = set()

    for session, resources in sessions:
        for resource in resources:
            if not resource.downloadable:
                continue
            if kinds is not None and resource.kind not in kinds:
                continue
            if only is not None and not only.search(resource.title):
                continue
            if resource.kind == 0 and not include_syllabus:
                continue

            folder = base / f"Sesion_{session:02d}"
            target = folder / build_filename(resource)
            counter = 2
            while target in used:
                stem, suffix = os.path.splitext(target.name)
                target = folder / f"{stem} ({counter}){suffix}"
                counter += 1
            used.add(target)
            items.append(DownloadItem(course=course, resource=resource, path=target))

    return items


# --------------------------------------------------------------------------- #
# Descarga
# --------------------------------------------------------------------------- #


def human_size(size: int | float) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def download_file(
    url: str,
    destination: Path,
    *,
    cookie_header: str = "",
    timeout: float = 60.0,
    retries: int = 3,
    referer: str = "",
) -> tuple[int, str]:
    """Descarga una URL a ``destination`` de forma atomica.

    Devuelve (bytes, sha256). Reintenta ante error de red o HTTP 5xx.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")

    last_error: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            headers = {
                "User-Agent": "autonoma-cli/0.1 (+uso-personal)",
                "Accept": "*/*",
                "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
            }
            if cookie_header:
                headers["Cookie"] = cookie_header
            if referer:
                headers["Referer"] = referer
            request = Request(url, headers=headers)
            digest = hashlib.sha256()
            size = 0
            with urlopen(request, timeout=timeout) as response, partial.open("wb") as handle:
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
        except (HTTPError, URLError, TimeoutError, OSError, CampusError) as exc:
            if _cert_mismatch(exc):
                _flush_dns()
            last_error = exc
            try:
                if partial.exists():
                    partial.unlink()
            except OSError:
                pass
            if isinstance(exc, HTTPError) and 400 <= exc.code < 500 and exc.code not in {408, 429}:
                break
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise CampusError(f"No se pudo descargar {url}: {last_error}")


@dataclass
class DownloadStats:
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    bytes: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)


def run_plan(
    items: Sequence[DownloadItem],
    manifest: Manifest,
    *,
    cookie_header: str,
    timeout: float = 60.0,
    workers: int = 1,
    force: bool = False,
    referer: str = "",
    on_event: Callable[[str, DownloadItem, str], None] | None = None,
) -> DownloadStats:
    """Ejecuta el plan. ``on_event`` recibe (tipo, item, detalle)."""

    stats = DownloadStats()

    def notify(kind: str, item: DownloadItem, detail: str = "") -> None:
        if on_event:
            on_event(kind, item, detail)

    def work(item: DownloadItem) -> tuple[str, DownloadItem, int, str]:
        entry = manifest.get(item.resource.url)
        if item.path.exists() and not force:
            known_size = int(entry.get("bytes", 0)) if entry else 0
            current_size = item.path.stat().st_size
            if not entry or not known_size or current_size == known_size:
                return "skip", item, current_size, ""
        size, sha = download_file(
            item.resource.url,
            item.path,
            cookie_header=cookie_header,
            timeout=timeout,
            referer=referer,
        )
        return "done", item, size, sha

    def register(item: DownloadItem, size: int, sha: str) -> None:
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

    workers = max(1, int(workers))
    if workers == 1 or len(items) == 1:
        for item in items:
            notify("start", item)
            try:
                status, item, size, sha = work(item)
            except CampusError as exc:
                stats.failed += 1
                stats.failures.append((str(item.path), str(exc)))
                notify("error", item, str(exc))
                continue
            if status == "skip":
                stats.skipped += 1
                notify("skip", item, human_size(size))
            else:
                stats.downloaded += 1
                stats.bytes += size
                register(item, size, sha)
                notify("done", item, human_size(size))
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(work, item): item for item in items}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    status, item, size, sha = future.result()
                except CampusError as exc:
                    stats.failed += 1
                    stats.failures.append((str(item.path), str(exc)))
                    notify("error", item, str(exc))
                    continue
                if status == "skip":
                    stats.skipped += 1
                    notify("skip", item, human_size(size))
                else:
                    stats.downloaded += 1
                    stats.bytes += size
                    register(item, size, sha)
                    notify("done", item, human_size(size))

    manifest.save()
    return stats

