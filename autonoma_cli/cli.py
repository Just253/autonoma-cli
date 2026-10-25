"""Interfaz de linea de comandos.

Comandos:
  login      guarda credenciales e inicia sesion
  logout     borra la cookie (y opcionalmente las credenciales)
  whoami     muestra la cuenta y el estado de la sesion
  cursos     lista los cursos del periodo
  curso      detalle de un curso y su silabo
  recursos   lista los recursos de un curso (por sesion)
  descargar  baja los archivos de un curso
  todo       baja los archivos de todos los cursos
  cache      gestiona la cache local
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import __version__, config
from .client import CampusClient
from .downloader import (
    Manifest,
    DownloadItem,
    human_size,
    plan_course,
    run_plan,
)
from .errors import AuthenticationError, AutonomaError, CampusError, UsageError
from .models import Course, Resource, SessionTopic
from . import ui

KIND_FILTERS: dict[str, set[int] | None] = {
    "archivo": {2},
    "tarea": {4},
    "evaluacion": {5},
    "foro": {7},
    "scorm": {10},
    "todo": None,
}

COURSE_CACHE_TTL = 6 * 3600


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def emit_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


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


def courses_cache_path() -> Path:
    return config.cache_dir() / "cursos.json"


def load_courses(client: CampusClient, *, refresh: bool = False) -> list[Course]:
    """Lista de cursos con cache de 6 horas (el campus responde lento)."""

    path = courses_cache_path()
    if not refresh and path.exists():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            fresh = time.time() - float(document.get("fetched_at", 0)) < COURSE_CACHE_TTL
            if fresh and document.get("base_url") == client.base_url:
                items = document.get("items")
                if isinstance(items, list) and items:
                    return [
                        Course.from_api(item, client.base_url)
                        for item in items
                        if isinstance(item, dict)
                    ]
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    courses = client.get_courses()
    try:
        config.write_private_text(
            path,
            json.dumps(
                {
                    "fetched_at": time.time(),
                    "base_url": client.base_url,
                    "student_code": client.student_code,
                    "items": [course.raw for course in courses],
                },
                ensure_ascii=False,
            ),
        )
    except OSError:
        pass
    return courses


def resolve_course(courses: Sequence[Course], token: str) -> Course:
    """Acepta indice (1..N), nGruCodigo o texto libre."""

    token = (token or "").strip()
    if not token:
        raise UsageError("Indica un curso: indice, nGruCodigo o parte del nombre.")
    if token.isdigit():
        number = int(token)
        for course in courses:
            if str(course.group_id) == token:
                return course
        if 1 <= number <= len(courses):
            return courses[number - 1]
    matches = [course for course in courses if course.matches(token)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise UsageError(f"No hay ningun curso que coincida con {token!r}.")
    listing = "\n".join(f"  - {course.name} ({course.group_id})" for course in matches)
    raise UsageError(f"Varios cursos coinciden con {token!r}:\n{listing}")


def kind_filter(name: str) -> set[int] | None:
    try:
        return KIND_FILTERS[name]
    except KeyError as exc:
        raise UsageError(f"Tipo desconocido: {name}") from exc


def parse_sessions(values: Sequence[int] | None, maximum: int | None = None) -> list[int] | None:
    if not values:
        return None
    sessions: list[int] = []
    for value in values:
        if maximum is not None and not 1 <= value <= maximum:
            raise UsageError(f"La sesion {value} no existe en este curso (1..{maximum}).")
        if value not in sessions:
            sessions.append(value)
    return sessions


def print_course_header(course: Course) -> None:
    print(ui.bold(course.name))
    details = [
        f"{course.code}" if course.code else "",
        f"periodo {course.period}" if course.period else "",
        f"ciclo {course.cycle}" if course.cycle else "",
        f"grupo {course.group}",
        f"{course.credits} creditos" if course.credits else "",
        course.modality,
    ]
    print("  " + " · ".join(part for part in details if part))
    if course.teacher:
        contact = f" <{course.teacher_email}>" if course.teacher_email else ""
        print(f"  Docente: {course.teacher}{contact}")
    if course.start_date or course.end_date:
        print(f"  Periodo de clases: {course.start_date} → {course.end_date}")
    print(f"  nGruCodigo: {course.group_id} · recursos: {course.resources_count}")


def print_syllabus(topics: Sequence[SessionTopic]) -> None:
    rows = []
    for topic in topics:
        first_line = (topic.topic or "").splitlines()[0]
        rows.append(
            [
                topic.label,
                f"{topic.start_date} - {topic.end_date}",
                first_line[:70],
                "*" if topic.active else "",
            ]
        )
    print()
    print(ui.table(["Ses.", "Semana", "Tema", "Act."], rows, max_widths=[5, 23, 70, 4]))


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


# --------------------------------------------------------------------------- #
# Comandos
# --------------------------------------------------------------------------- #


def cmd_login(args: argparse.Namespace) -> int:
    saved = config.load_credentials()
    username = args.usuario or (saved.username if saved else "") or input("Usuario: ").strip()

    password = args.password
    if not password:
        if saved and saved.username == username and saved.password:
            password = saved.password
        else:
            password = getpass.getpass("Contrasena: ")

    settings = config.load_settings()
    client = CampusClient(
        base_url=args.base_url or settings.base_url,
        timeout=args.timeout if args.timeout is not None else settings.timeout,
        delay=args.delay if args.delay is not None else settings.delay,
    )
    client.authenticate(username, password, force_login=True)

    if args.no_guardar:
        print(ui.yellow("Sesion iniciada, pero no se guardaron las credenciales."))
    else:
        stored = config.save_credentials(username, password)
        print(ui.green("Credenciales guardadas: ") + stored.storage_label)
        active = config.load_credentials()
        if active is not None and active.method == "plain_file":
            print(
                ui.yellow(
                    f"aviso: {config.plain_credentials_path()} existe y tiene prioridad. "
                    "Editalo o borralo para usar las credenciales cifradas."
                )
            )

    code = client.student_code or "(no detectado)"
    print(f"Sesion iniciada como {username} · codigo {code}")
    print(f"Cookie: {config.cookies_path()}")
    client.close()
    return 0


def cmd_logout(args: argparse.Namespace) -> int:
    client = CampusClient(base_url=args.base_url or config.load_settings().base_url)
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


def cmd_whoami(args: argparse.Namespace) -> int:
    client = client_for(args)
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
        emit_json(payload)
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


def cmd_credenciales(args: argparse.Namespace) -> int:
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
        emit_json(
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


def cmd_cursos(args: argparse.Namespace) -> int:
    client = client_for(args)
    courses = load_courses(client, refresh=args.refresh)
    if args.json:
        emit_json([course.to_dict() for course in courses])
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
    print(
        ui.table(
            ["#", "Curso", "Codigo", "Grupo", "Ciclo", "Docente", "Rec."],
            rows,
            max_widths=[3, 44, 12, 8, 5, 24, 4],
            aligns=["right", "left", "left", "left", "right", "left", "right"],
        )
    )
    print()
    print(ui.dim(f"Usa el indice o el nGruCodigo: autonoma recursos {courses[0].group_id if courses else 'GRUPO'}"))
    return 0


def cmd_curso(args: argparse.Namespace) -> int:
    client = client_for(args)
    courses = load_courses(client)
    course = resolve_course(courses, args.curso)
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
        emit_json(
            {
                "course": course.to_dict(),
                "sessions": [topic.to_dict() for topic in topics],
                "active_session_resources": [item.to_dict() for item in active_resources],
            }
        )
        return 0

    print_course_header(course)
    if course.syllabus_url:
        print(f"  Silabo: {course.syllabus_url}")
    if topics:
        print_syllabus(topics)
    if active_resources:
        print(ui.dim(f"\nSesion activa ({active_resources[0].session_label}) · {len(active_resources)} recursos"))
    print()
    print(
        ui.dim(
            f"Siguiente paso: autonoma recursos {course.group_id} "
            f"| autonoma descargar {course.group_id}"
        )
    )
    return 0


def _resources_of(
    client: CampusClient,
    course: Course,
    sessions: Sequence[int] | None,
) -> list[tuple[int, list[Resource]]]:
    if sessions:
        return [(session, client.get_session_resources(course.group_id, session)) for session in sessions]
    return client.iter_session_resources(course.group_id)


def cmd_recursos(args: argparse.Namespace) -> int:
    client = client_for(args)
    courses = load_courses(client)
    course = resolve_course(courses, args.curso)
    sessions = parse_sessions(args.sesion)
    grouped = _resources_of(client, course, sessions)

    flat = [item for _, resources in grouped for item in resources]
    if args.json:
        emit_json({"course": course.to_dict(), "resources": [item.to_dict() for item in flat]})
        return 0

    print_course_header(course)
    total = 0
    for session, resources in grouped:
        label = f"Sesion {session:02d}"
        if not resources:
            print(ui.dim(f"\n{label} · sin recursos"))
            continue
        print(f"\n{ui.bold(label)} · {len(resources)} recursos")
        print(
            ui.table(
                ["Ses.", "Tipo", "Titulo", "Ext", "Fecha"],
                resource_rows(resources),
                max_widths=[4, 11, 60, 5, 10],
            )
        )
        total += len(resources)
    print()
    print(f"Total: {total} recursos en {len([1 for _, items in grouped if items])} sesiones.")
    print(ui.dim(f"Descargar: autonoma descargar {course.group_id} --tipo archivo"))
    return 0


def _plan(args: argparse.Namespace, client: CampusClient, course: Course) -> list[DownloadItem]:
    sessions = parse_sessions(args.sesion)
    grouped = _resources_of(client, course, sessions)
    pattern = re.compile(args.solo, re.I) if args.solo else None
    return plan_course(
        course,
        grouped,
        out_dir(args),
        kinds=kind_filter(args.tipo),
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
        print_course_header(course)
        items = _plan(args, client, course)
        all_items.extend(items)
        if not items:
            print(ui.yellow("  Sin archivos que coincidan con el filtro."))

    if not all_items:
        print("\nNada que descargar.")
        return 0

    if args.seco:
        print()
        print(
            ui.table(
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
            )
        )
        print(f"\n{len(all_items)} archivos · destino {root} (simulacion, nada descargado)")
        return 0

    print(f"\nDescargando {len(all_items)} archivos → {root}")
    stats = run_plan(
        all_items,
        manifest,
        cookie_header=client.cookie_header(),
        timeout=client.timeout,
        workers=args.workers,
        force=args.forzar,
        referer=client.referer,
        on_event=progress,
    )
    print_stats(stats)
    if args.json:
        emit_json(
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


def cmd_descargar(args: argparse.Namespace) -> int:
    client = client_for(args)
    courses = load_courses(client)
    course = resolve_course(courses, args.curso)
    return _download(args, client, [course])


def cmd_todo(args: argparse.Namespace) -> int:
    client = client_for(args)
    courses = load_courses(client, refresh=args.refresh)
    if args.curso:
        courses = [course for course in courses if course.matches(args.curso)]
        if not courses:
            raise UsageError(f"No hay cursos que coincidan con {args.curso!r}.")
    return _download(args, client, courses)


def cmd_cache(args: argparse.Namespace) -> int:
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
        emit_json({"dir": str(folder), "files": [file.name for file in files]})
        return 0
    print(f"Cache: {folder}")
    if not files:
        print("  (vacia)")
    for file in files:
        print(f"  {file.name} · {human_size(file.stat().st_size)}")
    return 0


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autonoma",
        description="Cursos y descargas del Campus Virtual de la Universidad Autonoma del Peru.",
        epilog="Las credenciales se guardan en el directorio de configuracion del usuario, "
        "nunca en el repositorio.",
    )
    parser.add_argument("--version", action="version", version=f"autonoma-cli {__version__}")
    parser.add_argument(
        "--base-url",
        default=None,
        help=f"URL del campus (por defecto {config.DEFAULT_BASE_URL})",
    )
    parser.add_argument("--timeout", type=float, default=None, help="Timeout por peticion en segundos")
    parser.add_argument("--delay", type=float, default=None, help="Pausa entre peticiones en segundos")
    parser.add_argument("--out", default=None, help="Carpeta de descargas (por defecto: descargas)")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--refresh", action="store_true", help="Ignora la cache de cursos")
    parser.add_argument("--no-color", action="store_true", help="Desactiva color")
    parser.add_argument("-v", "--verbose", action="count", default=0)

    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="Guardar credenciales e iniciar sesion")
    login.add_argument("--usuario", help="Usuario del campus")
    login.add_argument("-p", "--password", help="Contrasena (si se omite, se pide sin mostrarla)")
    login.add_argument("--no-guardar", action="store_true", help="No guardar las credenciales")
    login.set_defaults(func=cmd_login)

    logout = sub.add_parser("logout", help="Cerrar la sesion local")
    logout.add_argument("--credenciales", action="store_true", help="Borrar tambien las credenciales")
    logout.set_defaults(func=cmd_logout)

    whoami = sub.add_parser("whoami", help="Ver la cuenta y el estado de la sesion")
    whoami.set_defaults(func=cmd_whoami)

    credenciales = sub.add_parser(
        "credenciales",
        help="Crear o ver el archivo de credenciales editable a mano",
    )
    credenciales.add_argument("--borrar", action="store_true", help="Borrar credentials.txt")
    credenciales.add_argument("--abrir", action="store_true", help="Abrirlo con el editor del sistema")
    credenciales.set_defaults(func=cmd_credenciales)

    cursos = sub.add_parser("cursos", help="Listar los cursos del periodo", aliases=["ls"])
    cursos.set_defaults(func=cmd_cursos)

    curso = sub.add_parser("curso", help="Detalle y silabo de un curso")
    curso.add_argument("curso", help="Indice, nGruCodigo o parte del nombre")
    curso.set_defaults(func=cmd_curso)

    recursos = sub.add_parser("recursos", help="Listar recursos de un curso")
    recursos.add_argument("curso", help="Indice, nGruCodigo o parte del nombre")
    recursos.add_argument("-s", "--sesion", type=int, action="append", help="Sesion concreta (repetible)")
    recursos.set_defaults(func=cmd_recursos)

    descargar = sub.add_parser("descargar", help="Descargar archivos de un curso", aliases=["download"])
    descargar.add_argument("curso", help="Indice, nGruCodigo o parte del nombre")
    descargar.add_argument("-s", "--sesion", type=int, action="append", help="Sesion concreta (repetible)")
    descargar.add_argument(
        "-t",
        "--tipo",
        default="archivo",
        choices=sorted(KIND_FILTERS),
        help="Que descargar (por defecto: archivo)",
    )
    descargar.add_argument("--solo", help="Filtro regex sobre el titulo del recurso")
    descargar.add_argument("--incluir-silabo", action="store_true", help="Incluir el silabo del curso")
    descargar.add_argument("--seco", "--dry-run", dest="seco", action="store_true", help="Solo mostrar el plan")
    descargar.add_argument("-w", "--workers", type=int, default=None, help="Descargas en paralelo")
    descargar.add_argument("--forzar", action="store_true", help="Volver a bajar aunque exista")
    descargar.set_defaults(func=cmd_descargar)

    todo = sub.add_parser("todo", help="Descargar los archivos de todos los cursos", aliases=["all"])
    todo.add_argument("--curso", help="Limitar a cursos que coincidan con el texto")
    todo.add_argument("-s", "--sesion", type=int, action="append", help="Sesion concreta (repetible)")
    todo.add_argument(
        "-t",
        "--tipo",
        default="archivo",
        choices=sorted(KIND_FILTERS),
        help="Que descargar (por defecto: archivo)",
    )
    todo.add_argument("--solo", help="Filtro regex sobre el titulo del recurso")
    todo.add_argument("--incluir-silabo", action="store_true", help="Incluir el silabo del curso")
    todo.add_argument("--seco", "--dry-run", dest="seco", action="store_true", help="Solo mostrar el plan")
    todo.add_argument("-w", "--workers", type=int, default=None, help="Descargas en paralelo")
    todo.add_argument("--forzar", action="store_true", help="Volver a bajar aunque exista")
    todo.set_defaults(func=cmd_todo)

    cache = sub.add_parser("cache", help="Ver o borrar la cache local")
    cache.add_argument("--borrar", action="store_true", help="Borrar los archivos de cache")
    cache.set_defaults(func=cmd_cache)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    ui.configure_color(False if args.no_color else None)

    if hasattr(args, "workers") and getattr(args, "workers", None) is None:
        args.workers = config.load_settings().workers

    try:
        return int(args.func(args) or 0)
    except UsageError as exc:
        print(ui.red(f"error: {exc}"), file=sys.stderr)
        return 2
    except AuthenticationError as exc:
        print(ui.red(f"login: {exc}"), file=sys.stderr)
        print("Revisa tu usuario y contrasena con: autonoma login --usuario TU_USUARIO", file=sys.stderr)
        return 3
    except CampusError as exc:
        print(ui.red(f"campus: {exc}"), file=sys.stderr)
        return 4
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        return 130
    except AutonomaError as exc:
        print(ui.red(f"error: {exc}"), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
