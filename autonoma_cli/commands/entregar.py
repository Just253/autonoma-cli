"""Comando `entregar`: sube un archivo a una carpeta compartida o a una tarea.

Propone el plan con ``--seco`` y solo escribe con ``--confirmar``. La logica
HTTP y el contrato del campus viven en ``uploader.py`` y ``uploadform.py``.
"""

from __future__ import annotations

import argparse

from .. import render, uploader
from ..client import CampusClient
from ..errors import UsageError
from .data import catalog, resolve_any


def run_entregar(client: CampusClient, args: argparse.Namespace) -> int:
    if args.seco and args.confirmar:
        raise UsageError(
            "--seco y --confirmar no van juntos: --seco no sube nada y --confirmar "
            "sube. Elige uno."
        )
    if not args.seco and not args.confirmar:
        raise UsageError(
            "Para subir de verdad agrega --confirmar; con --seco solo se muestra el plan "
            "y no se toca el campus."
        )

    kind = "carpeta" if args.carpeta is not None else "tarea"
    if args.sesion is not None and kind != "carpeta":
        raise UsageError("--sesion solo vale con --carpeta: en tareas la semana no se usa.")
    # Antes de pedir el catalogo: un archivo invalido no gasta ni una peticion.
    uploader.precheck(
        args.archivo,
        kind,
        title=args.titulo,
        description=args.descripcion,
        param0=args.param0,
    )

    courses = catalog(client, refresh=args.refresh)
    course = resolve_any(client, courses, args.grupo, refresh=args.refresh)
    target = uploader.target_for(
        client,
        course,
        folder=args.carpeta,
        task=args.tarea,
        session=args.sesion,
    )
    plan = uploader.build_plan(
        course,
        target,
        args.archivo,
        args.titulo,
        args.descripcion,
        param0=args.param0,
    )

    if args.seco:
        if args.json:
            render.emit_json(plan.to_dict())
        else:
            render.print_upload_plan(plan)
        return 0

    result = uploader.deliver(client, plan)
    if args.json:
        render.emit_json(plan.to_dict(result=result))
    else:
        render.print_upload_result(plan, result)
    return 0
