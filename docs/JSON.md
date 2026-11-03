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
