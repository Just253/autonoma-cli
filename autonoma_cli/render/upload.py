"""Plan y resultado de una subida (`entregar`)."""

from __future__ import annotations

from .. import ui
from ..models import UploadPlan, UploadResult


def destination(plan: UploadPlan) -> str:
    if plan.target.kind == "tarea":
        return f"Tarea {plan.target.number}"
    return f"Carpeta {plan.target.number} (semana {plan.target.session})"


def print_upload_plan(plan: UploadPlan) -> None:
    print()
    print(ui.bold(f"{destination(plan)} · {plan.path.name} ({ui.human_size(plan.size)})"))
    print(ui.table(
        ["Campo", "Valor"],
        [
            ["Curso", f"{plan.course_name} · {plan.target.group_id}"],
            ["Destino", destination(plan)],
            ["Archivo", f"{plan.path} · .{plan.extension}"],
            ["Tamano", ui.human_size(plan.size)],
            ["Titulo", plan.title],
            ["Descripcion", plan.description],
            ["param0", plan.param0 or "(sin param0: se conserva el nombre)"],
        ],
        max_widths=[12, 88],
    ))
    for warning in plan.warnings:
        print(ui.yellow(f"  aviso: {warning}"))
    print()
    print(ui.dim("Simulacion (--seco): no se subio nada. Para subir: agrega --confirmar."))


def print_upload_result(plan: UploadPlan, result: UploadResult) -> None:
    print()
    print(f"{ui.green('[ok]')} {destination(plan)} · {result.saved_name}")
    if result.task_id is not None:
        print(f"  nRespTarea: {result.task_id}")
    if result.resource_id:
        print(f"  nDocLinNum: {result.resource_id}")
    if result.sync_note:
        print(ui.yellow(f"  aviso: {result.sync_note}"))
