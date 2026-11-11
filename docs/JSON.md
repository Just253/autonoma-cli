# Salida JSON

`--json` vale antes o después del comando (`autonoma --json cursos` o
`autonoma cursos --json`). Las claves van en snake_case e inglés: el
`nGruCodigo` del campus aparece como **`group_id`**, y el resto sigue el mismo
criterio (`name`, `teacher`, `room`).

| Comando | Forma del JSON |
|---------|----------------|
| `cursos` | lista de cursos |
| `curso` | `{"course", "sessions", "active_session_resources"}` |
| `recursos` | `{"course", "resources"}` |
| `horario` | `{"from", "to", "count", "sessions"}` |
| `historial` | lista de cursos de todos los periodos |
| `notas` | lista de cursos activos; con `CURSO`, el objeto del curso con `items`; con `--todos`, `{"courses", "closed"}`; con `--promedio`, `{"courses"\|"course", "official"}` (ver abajo) |
| `descargar` / `todo` | resumen final: `downloaded`, `skipped`, `failed`, `bytes`, `out`, `failures` |
| `entregar` | `{"dry_run", "course", "target", "file", "title", "description", "param0", "warnings", "result"}` (ver abajo) |
| `whoami` | cuenta y sesión |
| `cache` | `{"dir", "files"}` |
| `credenciales` | `{"path", "created", "loaded", "username", "template"}` |

## Campos

- **Curso**: `group_id`, `name`, `code`, `period`, `cycle`, `section`, `group`,
  `credits`, `modality`, `teacher`, `teacher_email`, `start_date`, `end_date`,
  `resources_count`, `state`, `syllabus_url`, `career`.
- **Recurso**: `title`, `kind` (número), `kind_name`, `session`,
  `session_label`, `resource_id`, `url`, `date`, `extension`, `itinerary`,
  `description`.
- **Sesión del sílabo**: `number`, `label`, `start_date`, `end_date`, `topic`,
  `goal`, `active`.
- **Sesión de horario**: `group_id`, `course`, `session`, `session_label`,
  `topic`, `date` (ISO), `weekday`, `weekday_name`, `start_time`, `end_time`,
  `time_range`, `kind`, `room`, `code`, `recorded`.
- **Curso del historial**: `group_id`, `name`, `code`, `period`, `cycle`,
  `section`, `group`, `credits`, `teacher`, `career`, `state`, `enrollment`,
  `grade`.
- **Notas de un curso**: `group_id`, `course`, `period`, `cycle`, `average`
  (texto tal cual del campus, `""` si no hay), `average_value`, `percent`,
  `updated`; el detalle agrega `items`.
- **Criterio de evaluación**: `criterion` (`EC`, `EP`, `EF`), `weight`, `grade`
  (texto, `"-"` sin calificar), `grade_value` (`null` sin calificar), `session`,
  `from`, `to`.
- **Curso cerrado**: `group_id`, `course`, `period`, `cycle`, `grade`,
  `grade_value`, `closed: true`.
- **Promedio oficial**: `accumulated`, `weighted`, `credits_weighted`,
  `credits_total`, `credits_approved`, `merit`, `cycles` (lista de
  `{"period", "average"}`).

## Notas

`average` y `average_value` son el **acumulado** (`nPromTotal`): la suma de
`nota × peso` de los criterios ya calificados, no un promedio. `percent` es el
avance del curso, no la nota. La nota final de un periodo cerrado llega por
`grade` (`nPromocional`), no por `average`.

Sin `CURSO`, una lista de los cursos activos:

```json
[
  {
    "group_id": 90000001,
    "course": "CURSO DE EJEMPLO UNO",
    "period": "209901",
    "cycle": "1",
    "average": "12.80",
    "average_value": 12.8,
    "percent": 50,
    "updated": "15/03/2099 19:30:00"
  }
]
```

Con `CURSO`, el mismo objeto más `items`, un elemento por criterio:

```json
{
  "group_id": 90000001,
  "course": "CURSO DE EJEMPLO UNO",
  "period": "209901",
  "cycle": "1",
  "average": "12.80",
  "average_value": 12.8,
  "percent": 50,
  "updated": "15/03/2099 19:30:00",
  "items": [
    {
      "criterion": "EC",
      "weight": 20.0,
      "grade": "16.00",
      "grade_value": 16.0,
      "session": 4,
      "from": "01/03/2099",
      "to": "03/03/2099"
    },
    {
      "criterion": "EF",
      "weight": 50.0,
      "grade": "-",
      "grade_value": null,
      "session": 16,
      "from": "01/06/2099",
      "to": "03/06/2099"
    }
  ]
}
```

Con `--todos` sin `--promedio`, el resultado es un objeto con los activos en
`courses` y los cerrados en `closed`, deduplicados por `group_id` contra los
activos:

```json
{
  "courses": [
    {
      "group_id": 90000001,
      "course": "CURSO DE EJEMPLO UNO",
      "period": "209901",
      "cycle": "1",
      "average": "12.80",
      "average_value": 12.8,
      "percent": 50,
      "updated": "15/03/2099 19:30:00"
    }
  ],
  "closed": [
    {
      "group_id": 90000011,
      "course": "CURSO DE EJEMPLO DOS",
      "period": "209801",
      "cycle": "1",
      "grade": "15",
      "grade_value": 15.0,
      "closed": true
    }
  ]
}
```

Con `--promedio`, el resultado se envuelve en `courses` (o `course` si se pidió
un curso) y `official`; si además va `--todos`, suma la clave `closed`:

```json
{
  "courses": [
    {
      "group_id": 90000001,
      "course": "CURSO DE EJEMPLO UNO",
      "period": "209901",
      "cycle": "1",
      "average": "12.80",
      "average_value": 12.8,
      "percent": 50,
      "updated": "15/03/2099 19:30:00"
    }
  ],
  "official": {
    "accumulated": 14.35,
    "weighted": 14.35,
    "credits_weighted": 90.0,
    "credits_total": 120.0,
    "credits_approved": 90.0,
    "merit": 12,
    "cycles": [
      { "period": "209901", "average": 13.5 }
    ]
  }
}
```

`notas CURSO` sobre un curso de periodo cerrado no tiene `items`: devuelve la
entrada cerrada (`grade`, `grade_value`, `closed: true`), envuelta en `course`
si se pidió `--promedio`.

## `descargar --seco`

`descargar --seco` no emite JSON: muestra el plan en texto y sale. El resumen
JSON aparece al terminar una descarga real.

## `entregar`

`--seco` y una subida real devuelven el mismo objeto; solo cambian `dry_run` y
`result`:

```json
{
  "dry_run": false,
  "course": {
    "group_id": 90000001,
    "name": "CURSO DE EJEMPLO UNO",
    "code": "PISOP00001"
  },
  "target": {
    "kind": "tarea",
    "number": 209901,
    "session": 0
  },
  "file": {
    "path": "entrega.zip",
    "name": "entrega.zip",
    "bytes": 25600,
    "extension": "zip"
  },
  "title": "ENTREGA DE EJEMPLO",
  "description": "Trabajo de ejemplo",
  "param0": null,
  "warnings": [],
  "result": {
    "saved_name": "209901_ENTREGA.zip",
    "resource_id": null,
    "task_id": 2099011,
    "synced": null,
    "sync_note": ""
  }
}
```

- `target.kind` es `carpeta` o `tarea`; `target.number` es el `nDocLinNum` del
  destino y `target.session` la semana (`nForoSesion`), `0` en tareas.
- `param0` es `null` si no se pasó: el campus conserva el nombre original.
- `warnings` trae avisos que no bloquean (por ejemplo, más de 5 MB en carpeta).
- Con `--seco`, `dry_run` es `true` y `result` es `null`.
- En carpeta, éxito = `result.resource_id` (`nDocLinNum` nuevo); en tarea,
  éxito = `result.task_id` (`nRespTarea`).
- `synced` es `true` si la vista nueva (Mongo) se actualizó en una carpeta,
  `false` si falló (el motivo queda en `sync_note`) y `null` en tareas, que no
  pasan por Mongo. La entrega ya está registrada en los tres casos.

Los errores (archivo inválido, curso ambiguo, rechazo del campus) no emiten
JSON: van por `stderr` con el código de salida correspondiente.
