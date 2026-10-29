"""Piezas compartidas por los comandos: cliente, carpeta de salida y reportes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import config, render, ui
from ..client import CampusClient
from ..errors import UsageError

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


def report_error(exc: BaseException, prefix: str = "error", *extra: str) -> None:
    render.text(ui.red(f"{prefix}: {exc}"), stream=sys.stderr)
    for line in extra:
        render.text(line, stream=sys.stderr)


def report_cancelled() -> None:
    render.text("\nCancelado.", stream=sys.stderr)
