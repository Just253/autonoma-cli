"""Cuenta del campus: `login`, `logout` y `whoami`."""

from __future__ import annotations

import argparse
import getpass

from .. import config, render, ui
from ..client import CampusClient


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
        render.text(ui.yellow("Sesion iniciada, pero no se guardaron las credenciales."))
    else:
        stored = config.save_credentials(username, password)
        render.text(ui.green("Credenciales guardadas: ") + stored.storage_label)
        active = config.load_credentials()
        if active is not None and active.method == "plain_file":
            render.text(ui.yellow(
                f"aviso: {config.plain_credentials_path()} existe y tiene prioridad. "
                "Editalo o borralo para usar las credenciales cifradas."
            ))

    code = client.student_code or "(no detectado)"
    render.text(f"Sesion iniciada como {username} · codigo {code}")
    render.text(f"Cookie: {config.cookies_path()}")
    client.close()
    return 0


def run_logout(client: CampusClient, args: argparse.Namespace) -> int:
    if client.forget_cookies():
        render.text(ui.green("Cookie de sesion borrada."))
    else:
        render.text("No habia cookie de sesion guardada.")
    if args.credenciales:
        removed = config.clear_credentials()
        removed_plain = config.clear_plain_credentials()
        if removed or removed_plain:
            render.text(ui.green("Credenciales eliminadas del disco."))
        else:
            render.text("No habia credenciales guardadas.")
    return 0


def run_whoami(client: CampusClient, args: argparse.Namespace) -> int:
    client.ensure_student_code()
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

    render.text(ui.bold("Cuenta del campus"))
    render.text(f"  Usuario:       {payload['username'] or '(no guardado)'}")
    render.text(f"  Codigo alumno: {payload['student_code'] or '(no detectado)'}")
    render.text(f"  Campus:        {payload['base_url']}")
    render.text(f"  Sesion:        activa (cookie en {payload['cookies_file']})")
    if credentials:
        label = credentials.get("label") or credentials.get("method", "")
        render.text(f"  Credenciales:  {credentials['username'] or '(sin usuario)'} · {label}")
        render.text(f"  Archivo:       {credentials['path']}")
        if not credentials.get("complete", True):
            render.text(ui.yellow("                 falta usuario o contrasena en ese archivo"))
    else:
        render.text("  Credenciales:  no guardadas (usa `autonoma credenciales` o variables de entorno)")
    render.text(f"  Config:        {payload['config_dir']}")
    return 0
