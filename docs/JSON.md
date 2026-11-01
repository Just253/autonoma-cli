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
  `section`, `group`, `credits`, `teacher`, `career`, `state`, `enrollment`.

`descargar --seco` no emite JSON: muestra el plan en texto y sale. El resumen
JSON aparece al terminar una descarga real.
