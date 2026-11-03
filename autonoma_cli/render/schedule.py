"""Tabla del horario por dia."""

from __future__ import annotations

import datetime as dt
from typing import Sequence

from .. import ui
from ..models import WEEKDAYS, ClassSession


def session_count(count: int) -> str:
    return f"{count} sesion" if count == 1 else f"{count} sesiones"


def print_schedule(
    entries: Sequence[ClassSession],
    start: dt.date | None,
    end: dt.date | None,
) -> None:
    today = dt.date.today()
    if start is None or end is None:
        heading = f"Horario completo · {session_count(len(entries))}"
    elif start == end:
        label = "Hoy" if start == today else WEEKDAYS[start.weekday()].capitalize()
        heading = f"{label}, {start:%d/%m/%Y}"
        if entries:
            heading += f" · {session_count(len(entries))}"
    else:
        heading = f"Del {start:%d/%m/%Y} al {end:%d/%m/%Y} · {session_count(len(entries))}"
    print(ui.bold(heading))

    if not entries:
        where = "para esa fecha" if start == end else "en ese rango"
        if start is None or end is None:
            where = "en el periodo"
        print(ui.yellow(f"Sin clases {where}."))
        return

    grouped: list[tuple[dt.date, list[ClassSession]]] = []
    for entry in entries:
        day = entry.date_value
        if day is None:
            continue
        if grouped and grouped[-1][0] == day:
            grouped[-1][1].append(entry)
        else:
            grouped.append((day, [entry]))

    for day, items in grouped:
        print()
        print(ui.bold(f"{WEEKDAYS[day.weekday()].capitalize()} {day:%d/%m/%Y}"))
        rows = [
            [
                entry.time_range or "-",
                entry.course,
                entry.room or "-",
                entry.kind or "-",
                entry.label,
            ]
            for entry in items
        ]
        print(
            ui.table(
                ["Hora", "Curso", "Aula", "Tipo", "Ses."],
                rows,
                max_widths=[13, 46, 32, 12, 4],
            )
        )

    if start is not None and start == end:
        print()
        for entry in entries:
            print(ui.dim(f"  {entry.label} · {entry.title[:96]}"))
