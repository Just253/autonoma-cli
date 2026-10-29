"""Comando `credenciales`: archivo editable a mano."""

from __future__ import annotations

import argparse
import os
import subprocess

from .. import config, render, ui
from ..client import CampusClient


def run_credenciales(client: CampusClient | None, args: argparse.Namespace) -> int:
    """Crea y muestra el archivo de credenciales editable a mano."""

    if args.borrar:
        removed = config.clear_plain_credentials()
        if removed:
            render.text(ui.green("credentials.txt eliminado."))
        else:
            render.text("No existia credentials.txt.")
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
            render.text(ui.yellow(f"No se pudo abrir el editor: {exc}"))

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

    render.text(ui.bold("Archivo de credenciales editable"))
    render.text(f"  {path}" + (ui.green("  (creado ahora)") if created else "  (ya existia)"))
    render.text()
    render.text("Completa estas dos lineas y guarda:")
    render.text(ui.cyan("  usuario=tu-codigo-de-alumno"))
    render.text(ui.cyan("  password=tu-clave"))
    render.text()
    if editable:
        render.text(ui.green(f"Ahora mismo carga: {editable.username} (texto plano)"))
    else:
        render.text(ui.yellow("Todavia falta usuario o contrasena en el archivo."))
    render.text(ui.dim("Tiene prioridad sobre las credenciales cifradas de `autonoma login`."))
    render.text(ui.dim("Es texto plano: no lo compartas ni lo subas a un repo."))
    return 0
