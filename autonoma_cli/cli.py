"""Interfaz de linea de comandos.

Comandos:
  login      guarda credenciales e inicia sesion
  logout     borra la cookie (y opcionalmente las credenciales)
  whoami     muestra la cuenta y el estado de la sesion
  credenciales  crea o muestra el archivo de credenciales editable a mano
  cursos     lista los cursos del periodo
  curso      detalle de un curso y su silabo
  horario    fechas, horas y aulas de las sesiones
  recursos   lista los recursos de un curso (por sesion)
  descargar  baja los archivos de un curso
  todo       baja los archivos de todos los cursos
  cache      gestiona la cache local

Aqui solo vive el parser y el despacho: cada subparser declara su funcion con
``set_defaults`` y ``main`` construye el cliente una sola vez.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__, commands, config, selectors, ui
from .client import CampusClient
from .errors import AuthenticationError, AutonomaError, CampusError, UsageError


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #


def _add_download_options(subparser: argparse.ArgumentParser) -> None:
    """Opciones compartidas por `descargar` y `todo`."""

    subparser.add_argument("-s", "--sesion", type=int, action="append", help="Sesion concreta (repetible)")
    subparser.add_argument(
        "-t",
        "--tipo",
        default="archivo",
        choices=sorted(selectors.KIND_FILTERS),
        help="Que descargar (por defecto: archivo)",
    )
    subparser.add_argument("--solo", help="Filtro regex sobre el titulo del recurso")
    subparser.add_argument("--incluir-silabo", action="store_true", help="Incluir el silabo del curso")
    subparser.add_argument("--seco", "--dry-run", dest="seco", action="store_true", help="Solo mostrar el plan")
    subparser.add_argument("-w", "--workers", type=int, default=None, help="Descargas en paralelo")
    subparser.add_argument("--forzar", action="store_true", help="Volver a bajar aunque exista")
    subparser.add_argument("--out", default=argparse.SUPPRESS,
                           help="Carpeta de descargas (por defecto: descargas)")


def _add_shared_options(subparser: argparse.ArgumentParser) -> None:
    """Opciones de la raiz que tambien valen despues del comando.

    Se repiten visibles en la ayuda (como los *persistent flags* de cobra), con
    ``SUPPRESS`` para que el subparser no pise el valor que el parser raiz ya
    resolvio cuando la opcion viene antes del comando.
    """

    subparser.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                           help="Salida JSON")
    subparser.add_argument("--no-color", action="store_true", default=argparse.SUPPRESS,
                           help="Desactiva color")


def _add_course_filters(subparser: argparse.ArgumentParser, *, active: bool = True) -> None:
    """Filtros para separar cursos de otro ciclo, periodo o carrera."""

    subparser.add_argument("--ciclo", help="Solo los cursos de ese ciclo (por ejemplo 8)")
    subparser.add_argument("--periodo", help="Solo los cursos de ese periodo (por ejemplo 209901)")
    subparser.add_argument("--carrera", help="Solo cursos cuya carrera contenga el texto")
    if active:
        subparser.add_argument("--activos", action="store_true", help="Solo los cursos activos")


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
    login.set_defaults(func=commands.run_login, authenticate=False)

    logout = sub.add_parser("logout", help="Cerrar la sesion local")
    logout.add_argument("--credenciales", action="store_true", help="Borrar tambien las credenciales")
    logout.set_defaults(func=commands.run_logout, authenticate=False)

    whoami = sub.add_parser("whoami", help="Ver la cuenta y el estado de la sesion")
    whoami.set_defaults(func=commands.run_whoami)

    credenciales = sub.add_parser(
        "credenciales",
        help="Crear o ver el archivo de credenciales editable a mano",
    )
    credenciales.add_argument("--borrar", action="store_true", help="Borrar credentials.txt")
    credenciales.add_argument("--abrir", action="store_true", help="Abrirlo con el editor del sistema")
    credenciales.set_defaults(func=commands.run_credenciales, needs_client=False)

    cursos = sub.add_parser("cursos", help="Listar los cursos del periodo", aliases=["ls"])
    cursos.set_defaults(func=commands.run_cursos)

    curso = sub.add_parser("curso", help="Detalle y silabo de un curso")
    curso.add_argument("curso", help="Indice, nGruCodigo o parte del nombre")
    curso.set_defaults(func=commands.run_curso)

    horario = sub.add_parser("horario", help="Horario de clases y aulas", aliases=["aula"])
    horario.add_argument(
        "curso",
        nargs="?",
        help="Limitar a un curso (indice, nGruCodigo o parte del nombre)",
    )
    rango = horario.add_mutually_exclusive_group()
    rango.add_argument("--hoy", action="store_true", help="Solo las clases de hoy")
    rango.add_argument("--manana", action="store_true", help="Solo las clases de manana")
    rango.add_argument("--dia", help="Un dia concreto (dd/mm/aaaa)")
    rango.add_argument("--todo", action="store_true", help="Todo el periodo")
    horario.add_argument("--desde", help="Desde esta fecha (dd/mm/aaaa)")
    horario.add_argument("--hasta", help="Hasta esta fecha (dd/mm/aaaa)")
    horario.set_defaults(func=commands.run_horario)

    recursos = sub.add_parser("recursos", help="Listar recursos de un curso")
    recursos.add_argument("curso", help="Indice, nGruCodigo o parte del nombre")
    recursos.add_argument("-s", "--sesion", type=int, action="append", help="Sesion concreta (repetible)")
    recursos.set_defaults(func=commands.run_recursos)

    descargar = sub.add_parser("descargar", help="Descargar archivos de un curso", aliases=["download"])
    descargar.add_argument("curso", help="Indice, nGruCodigo o parte del nombre")
    _add_download_options(descargar)
    descargar.set_defaults(func=commands.run_descargar)

    todo = sub.add_parser("todo", help="Descargar los archivos de todos los cursos", aliases=["all"])
    todo.add_argument("--curso", help="Limitar a cursos que coincidan con el texto")
    _add_download_options(todo)
    todo.set_defaults(func=commands.run_todo)

    cache_cmd = sub.add_parser("cache", help="Ver o borrar la cache local")
    cache_cmd.add_argument("--borrar", action="store_true", help="Borrar los archivos de cache")
    cache_cmd.set_defaults(func=commands.run_cache, needs_client=False)

    historial = sub.add_parser(
        "historial",
        help="Cursos de todos los periodos (aprobados y en curso)",
    )
    historial.add_argument("--curso", help="Filtra por texto del nombre o nGruCodigo")
    historial.set_defaults(func=commands.run_historial)

    for command in (cursos, curso, horario, recursos, descargar, todo):
        command.add_argument("--refresh", action="store_true", default=argparse.SUPPRESS,
                             help="Ignora la cache")  # SUPPRESS: no pisa el --refresh global

    for command in (login, logout, whoami, credenciales, cursos, curso, horario,
                    recursos, descargar, todo, cache_cmd, historial):
        _add_shared_options(command)

    for command in (cursos, horario, todo):
        _add_course_filters(command)
    _add_course_filters(historial, active=False)

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

    try:
        client: CampusClient | None = None
        if getattr(args, "needs_client", True):
            client = commands.client_for(
                args, authenticate=getattr(args, "authenticate", True)
            )
        return int(args.func(client, args) or 0)
    except UsageError as exc:
        commands.report_error(exc)
        return 2
    except AuthenticationError as exc:
        commands.report_error(exc, "login", commands.LOGIN_HINT)
        return 3
    except CampusError as exc:
        commands.report_error(exc, "campus")
        return 4
    except KeyboardInterrupt:
        commands.report_cancelled()
        return 130
    except AutonomaError as exc:
        commands.report_error(exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
