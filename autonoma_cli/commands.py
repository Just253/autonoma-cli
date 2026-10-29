"""Implementacion de los comandos de la CLI.

Cada comando es una funcion ``run_x(client, args) -> int``. El cliente lo
construye ``cli.main`` con :func:`client_for` y se inyecta: ningun comando
instancia ``CampusClient``. Este modulo no importa ``cli`` (evita el ciclo).
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from . import cache, config, render, selectors, ui
from .client import CampusClient
from .downloader import DownloadItem, Manifest, human_size, plan_course, run_plan
from .errors import UsageError
from .models import ClassSession, Course, Resource

LOGIN_HINT = "Revisa tu usuario y contrasena con: autonoma login --usuario TU_USUARIO"


def client_for(args: argparse.Namespace, *, authenticate: bool = True) -> CampusClient:
    settings = config.load_settings()
    client = CampusClient(
        base_url=args.base_url or settings.base_url,
        timeout=args.timeout if args.timeout is not None else settings.timeout,
        delay=args.delay if args.delay is not None else settings.delay,
    )
    if not authenticate:
        return client

    credentials = config.load_credentials()
    if credentials is None:
        raise UsageError(
            "No hay credenciales guardadas. Ejecuta `autonoma login` o define "
            "AUTONOMA_USER y AUTONOMA_PASSWORD."
        )
    client.authenticate(credentials.username, credentials.password)
    return client


def out_dir(args: argparse.Namespace) -> Path:
    raw = args.out or config.load_settings().out_dir
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def catalog(client: CampusClient, *, refresh: bool = False) -> list[Course]:
    """Cursos del periodo con cache de 6 horas (el campus responde lento)."""
    items = cache.ensure(
        cache.for_campus(client.base_url),
        f"cursos:{client.student_code}",
        ttl=cache.MAX_AGE_CURSOS,
        fetch=lambda: [dict(course.raw or {}) for course in client.get_courses()],
        force=refresh,
    )
    records = items if isinstance(items, list) else []
    return [Course.from_api(item, client.base_url) for item in records if isinstance(item, dict)]


def schedule(
    client: CampusClient, courses: Sequence[Course], *, refresh: bool = False
) -> list[ClassSession]:
    """Programacion de todos los cursos, con cache de 6 horas por grupo."""
    store = cache.for_campus(client.base_url)
    entries: list[ClassSession] = []
    for course in courses:
        records = cache.ensure(
            store,
            f"horario:{course.group_id}",
            ttl=cache.MAX_AGE_HORARIO,
            fetch=lambda course=course: [
                dict(entry.raw or {})
                for entry in client.get_schedule(course.group_id, course=course.name)
            ],
            force=refresh,
        )
        entries.extend(
            ClassSession.from_api(item, group_id=course.group_id, course=course.name)
            for item in (records if isinstance(records, list) else ()) if isinstance(item, dict)
        )
    return entries


def _resources_of(
    client: CampusClient, course: Course, sessions: Sequence[int] | None
) -> list[tuple[int, list[Resource]]]:
    if sessions:
        return [(session, client.get_session_resources(course.group_id, session)) for session in sessions]
    return client.iter_session_resources(course.group_id)


def _plan(args: argparse.Namespace, client: CampusClient, course: Course) -> list[DownloadItem]:
    sessions = selectors.parse_sessions(args.sesion)
    grouped = _resources_of(client, course, sessions)
    pattern = re.compile(args.solo, re.I) if args.solo else None
    return plan_course(
        course,
        grouped,
        out_dir(args),
        kinds=selectors.kind_filter(args.tipo),
        only=pattern,
        include_syllabus=args.incluir_silabo,
    )


def _download(args: argparse.Namespace, client: CampusClient, courses: Sequence[Course]) -> int:
    root = out_dir(args)
    root.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(root)
    all_items: list[DownloadItem] = []

    for course in courses:
        print()
        render.print_course_header(course)
        items = _plan(args, client, course)
        all_items.extend(items)
        if not items:
            print(ui.yellow("  Sin archivos que coincidan con el filtro."))

    if not all_items:
        print("\nNada que descargar.")
        return 0

    if args.seco:
        print()
        print(ui.table(
            ["Curso", "Ses.", "Tipo", "Archivo"],
            [
                [
                    item.course.name[:28],
                    item.resource.session_label,
                    item.resource.kind_name,
                    str(item.path.relative_to(root)),
                ]
                for item in all_items
            ],
            max_widths=[28, 4, 11, 90],
        ))
        print(f"\n{len(all_items)} archivos · destino {root} (simulacion, nada descargado)")
        return 0

    print(f"\nDescargando {len(all_items)} archivos → {root}")
    stats = run_plan(
        all_items,
        manifest,
        cookie_header=client.cookie_header(),
        timeout=client.timeout,
        workers=args.workers if args.workers is not None else config.load_settings().workers,
        force=args.forzar,
        referer=client.referer,
        on_event=render.progress,
    )
    render.print_stats(stats)
    if args.json:
        render.emit_json(
            {
                "downloaded": stats.downloaded,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "bytes": stats.bytes,
                "out": str(root),
                "failures": stats.failures,
            }
        )
    return 0 if stats.failed == 0 else 1


def report_error(exc: BaseException, prefix: str = "error", *extra: str) -> None:
    print(ui.red(f"{prefix}: {exc}"), file=sys.stderr)
    for line in extra:
        print(line, file=sys.stderr)


def report_cancelled() -> None:
    print("\nCancelado.", file=sys.stderr)


def run_login(client: CampusClient, args: argparse.Namespace) -> int:
    saved = config.load_credentials()
    username = args.usuario or (saved.username if saved else "") or input("Usuario: ").strip()

    password = args.password
    if not password:
        if saved and saved.username == username and saved.password:
            password = saved.password
        else:
            password = getpass.getpass("Contrasena: ")

    client.authenticate(username, password, force_login=True)

    if args.no_guardar:
        print(ui.yellow("Sesion iniciada, pero no se guardaron las credenciales."))
    else:
        stored = config.save_credentials(username, password)
        print(ui.green("Credenciales guardadas: ") + stored.storage_label)
        active = config.load_credentials()
        if active is not None and active.method == "plain_file":
            print(ui.yellow(
                f"aviso: {config.plain_credentials_path()} existe y tiene prioridad. "
                "Editalo o borralo para usar las credenciales cifradas."
            ))

    code = client.student_code or "(no detectado)"
    print(f"Sesion iniciada como {username} · codigo {code}")
    print(f"Cookie: {config.cookies_path()}")
    client.close()
    return 0


def run_logout(client: CampusClient, args: argparse.Namespace) -> int:
    if client.forget_cookies():
        print(ui.green("Cookie de sesion borrada."))
    else:
        print("No habia cookie de sesion guardada.")
    if args.credenciales:
        removed = config.clear_credentials()
        removed_plain = config.clear_plain_credentials()
        if removed or removed_plain:
            print(ui.green("Credenciales eliminadas del disco."))
        else:
            print("No habia credenciales guardadas.")
    return 0


def run_whoami(client: CampusClient, args: argparse.Namespace) -> int:
    info = client.describe()
    credentials = config.credentials_info()

    payload = {
        "username": credentials.get("username") if credentials else None,
        "student_code": client.student_code or None,
        "session": "activa",
        "base_url": info["base_url"],
        "credentials": credentials,
        "cookies_file": info["cookies_file"],
        "config_dir": str(config.home()),
    }
    if args.json:
        render.emit_json(payload)
        return 0

    print(ui.bold("Cuenta del campus"))
    print(f"  Usuario:       {payload['username'] or '(no guardado)'}")
    print(f"  Codigo alumno: {payload['student_code'] or '(no detectado)'}")
    print(f"  Campus:        {payload['base_url']}")
    print(f"  Sesion:        activa (cookie en {payload['cookies_file']})")
    if credentials:
        label = credentials.get("label") or credentials.get("method", "")
        print(f"  Credenciales:  {credentials['username'] or '(sin usuario)'} · {label}")
        print(f"  Archivo:       {credentials['path']}")
        if not credentials.get("complete", True):
            print(ui.yellow("                 falta usuario o contrasena en ese archivo"))
    else:
        print("  Credenciales:  no guardadas (usa `autonoma credenciales` o variables de entorno)")
    print(f"  Config:        {payload['config_dir']}")
    return 0


def run_credenciales(client: CampusClient | None, args: argparse.Namespace) -> int:
    """Crea y muestra el archivo de credenciales editable a mano."""

    if args.borrar:
        removed = config.clear_plain_credentials()
        if removed:
            print(ui.green("credentials.txt eliminado."))
        else:
            print("No existia credentials.txt.")
        return 0

    path, created = config.create_plain_credentials_file()
    editable = config.read_plain_credentials()

    if args.abrir:
        try:
            if os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        except Exception as exc:  # noqa: BLE001 - abrir el editor es opcional
            print(ui.yellow(f"No se pudo abrir el editor: {exc}"))

    if args.json:
        render.emit_json(
            {
                "path": str(path),
                "created": created,
                "loaded": editable is not None,
                "username": editable.username if editable else "",
                "template": config.PLAIN_CREDENTIALS_TEMPLATE,
            }
        )
        return 0

    print(ui.bold("Archivo de credenciales editable"))
    print(f"  {path}" + (ui.green("  (creado ahora)") if created else "  (ya existia)"))
    print()
    print("Completa estas dos lineas y guarda:")
    print(ui.cyan("  usuario=tu-codigo-de-alumno"))
    print(ui.cyan("  password=tu-clave"))
    print()
    if editable:
        print(ui.green(f"Ahora mismo carga: {editable.username} (texto plano)"))
    else:
        print(ui.yellow("Todavia falta usuario o contrasena en el archivo."))
    print(ui.dim("Tiene prioridad sobre las credenciales cifradas de `autonoma login`."))
    print(ui.dim("Es texto plano: no lo compartas ni lo subas a un repo."))
    return 0


def run_cursos(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    if args.json:
        render.emit_json([course.to_dict() for course in courses])
        return 0

    print(ui.bold(f"{len(courses)} cursos · periodo {courses[0].period if courses else '-'}"))
    rows = [
        [
            index,
            course.name[:44],
            course.code,
            course.group,
            course.cycle,
            course.teacher[:24],
            course.resources_count,
        ]
        for index, course in enumerate(courses, start=1)
    ]
    print()
    print(ui.table(
        ["#", "Curso", "Codigo", "Grupo", "Ciclo", "Docente", "Rec."],
        rows,
        max_widths=[3, 44, 12, 8, 5, 24, 4],
        aligns=["right", "left", "left", "left", "right", "left", "right"],
    ))
    print()
    print(ui.dim(f"Usa el indice o el nGruCodigo: autonoma recursos {courses[0].group_id if courses else 'GRUPO'}"))
    return 0


def run_curso(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    course = selectors.resolve_course(courses, args.curso)
    topics = client.get_syllabus(course.group_id)
    detail = client.get_course_detail(course.group_id, 0)
    active_resources: list[Resource] = []
    if isinstance(detail, dict):
        raw_records = detail.get("recursos")
        if isinstance(raw_records, list):
            active_resources = [
                Resource.from_api(item, client.base_url)
                for item in raw_records
                if isinstance(item, dict)
            ]

    if args.json:
        render.emit_json(
            {
                "course": course.to_dict(),
                "sessions": [topic.to_dict() for topic in topics],
                "active_session_resources": [item.to_dict() for item in active_resources],
            }
        )
        return 0

    render.print_course_header(course)
    if course.syllabus_url:
        print(f"  Silabo: {course.syllabus_url}")
    if topics:
        render.print_syllabus(topics)
    if active_resources:
        print(ui.dim(f"\nSesion activa ({active_resources[0].session_label}) · {len(active_resources)} recursos"))
    print()
    print(
        ui.dim(
            f"Siguiente paso: autonoma horario {course.group_id} "
            f"| autonoma recursos {course.group_id} "
            f"| autonoma descargar {course.group_id}"
        )
    )
    return 0


def run_horario(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    if args.curso:
        courses = [selectors.resolve_course(courses, args.curso)]
    else:
        active = [course for course in courses if course.state == "activo"]
        courses = active or courses
    entries = schedule(client, courses, refresh=args.refresh)

    start, end = selectors.schedule_range(args)
    if start is not None and end is not None:
        entries = [
            entry
            for entry in entries
            if entry.date_value is not None and start <= entry.date_value <= end
        ]
    entries.sort(key=lambda entry: entry.sort_key())

    if args.json:
        render.emit_json(
            {
                "from": start.isoformat() if start else None,
                "to": end.isoformat() if end else None,
                "count": len(entries),
                "sessions": [entry.to_dict() for entry in entries],
            }
        )
        return 0

    render.print_schedule(entries, start, end)
    print()
    print(ui.dim("Opciones: --hoy | --manana | --dia dd/mm/aaaa | --desde/--hasta | --todo"))
    return 0


def run_recursos(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    course = selectors.resolve_course(courses, args.curso)
    sessions = selectors.parse_sessions(args.sesion)
    grouped = _resources_of(client, course, sessions)

    flat = [item for _, resources in grouped for item in resources]
    if args.json:
        render.emit_json({"course": course.to_dict(), "resources": [item.to_dict() for item in flat]})
        return 0

    render.print_course_header(course)
    total = 0
    for session, resources in grouped:
        label = f"Sesion {session:02d}"
        if not resources:
            print(ui.dim(f"\n{label} · sin recursos"))
            continue
        print(f"\n{ui.bold(label)} · {len(resources)} recursos")
        print(ui.table(
            ["Ses.", "Tipo", "Titulo", "Ext", "Fecha"],
            render.resource_rows(resources),
            max_widths=[4, 11, 60, 5, 10],
        ))
        total += len(resources)
    print()
    print(f"Total: {total} recursos en {len([1 for _, items in grouped if items])} sesiones.")
    print(ui.dim(f"Descargar: autonoma descargar {course.group_id} --tipo archivo"))
    return 0


def run_descargar(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    course = selectors.resolve_course(courses, args.curso)
    return _download(args, client, [course])


def run_todo(client: CampusClient, args: argparse.Namespace) -> int:
    courses = catalog(client, refresh=args.refresh)
    if args.curso:
        courses = [course for course in courses if course.matches(args.curso)]
        if not courses:
            raise UsageError(f"No hay cursos que coincidan con {args.curso!r}.")
    return _download(args, client, courses)


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
        print(f"Cache borrada: {removed} archivos en {folder}")
        return 0
    if args.json:
        render.emit_json({"dir": str(folder), "files": [file.name for file in files]})
        return 0
    print(f"Cache: {folder}")
    if not files:
        print("  (vacia)")
    for file in files:
        print(f"  {file.name} · {human_size(file.stat().st_size)}")
    return 0
