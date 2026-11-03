# Desarrollo

## Cómo encaja todo

```
cli.py  →  commands/  →  cache.py, render.py, selectors.py, client.py, downloader.py
                 ↓
              config/, models.py, ui.py, errors.py
```

`cli.main` construye el parser, resuelve el cliente una sola vez
(`commands.client_for`) y despacha con `args.func(client, args)`. Ningún comando
instancia `CampusClient` ni imprime: la salida pasa por `render` y las tablas de
`ui`.

```
autonoma_cli/
├── cli.py              # parser y despacho (sin lógica de negocio)
├── commands/           # un módulo por tema: run_*(client, args)
│   ├── base.py         # cliente, carpeta de salida, reportes
│   ├── data.py         # cursos, horario, historial y resolución de cursos
│   └── …               # account, courses, history, timetable, resources, grades, download, maintenance, credenciales
├── config/             # rutas, io atómico, DPAPI, credenciales, settings
├── client.py           # login ASP.NET, cookies y WebMethods
├── models.py           # Course, HistoryCourse, CourseGrades, AcademicSummary, recursos y horario
├── downloader.py       # plan, descarga atómica, manifiesto y sha256
├── cache.py            # cache.json (cursos, horario, historial)
├── render.py           # tablas y salida JSON
├── selectors.py        # filtros de curso, sesión, tipo y fechas
├── ui.py               # tablas y color
└── errors.py           # errores tipados
```

## La guardia de arquitectura

`tests/test_architecture.py` no prueba comportamiento: fija dónde vive cada
cosa. Si algo falla, el mensaje dice qué hacer. Reglas principales:

- `cli.py` ≤ 260 líneas, cada `commands/*.py` ≤ 120, cada `config/*.py` ≤ 200.
- `cli.py` y `commands/` no imprimen: usan `render` o `ui`.
- JSON a mano solo en `cache.py`, `client.py`, `downloader.py` y `render.py`.
- Solo `cli.py` importa `commands`; solo `cli.py` y `__main__.py` importan
  `cli.py`.
- Todo `run_*` recibe `client` primero y se reexporta en `commands/__init__.py`.
- `CampusClient` se instancia únicamente en `commands/base.py`.
- Cada subpaquete tiene `__init__.py` (si no, el wheel no lo incluye).

## Pruebas

```powershell
py -3.12 -m pytest -q
py -3.11 -m unittest discover -s tests
```

No tocan la red: usan clientes falsos y `AUTONOMA_CLI_HOME` temporal. Hay un
skip en Windows (permisos POSIX).

`tests/test_docs.py` ejecuta los ejemplos `autonoma …` de todos los Markdown del
repo: si un ejemplo deja de parsear, el test falla. Por eso, al cambiar un flag,
hay que actualizar [CLI.md](CLI.md).

## Agregar un comando

1. Crear `commands/<tema>.py` con `run_<nombre>(client, args) -> int`.
2. Reexportarlo en `commands/__init__.py`.
3. Declararlo en `build_parser` (`cli.py`) con sus flags y `set_defaults`.
4. Documentarlo en [CLI.md](CLI.md) y, si tiene flujo propio, en [GUIA.md](GUIA.md).
5. Test: parser + comando con cliente falso.

## Convenciones del repo

- Mensajes de commit en ASCII, imperativo y con el porqué en el cuerpo.
- Documentación en español con acentos; código y nombres de archivo sin acentos.
- **Datos ficticios** en tests y ejemplos: nunca `nGruCodigo`, docentes, aulas,
  carreras ni periodos reales.
- `docs/` es la fuente de verdad de la documentación; ver el mapa en
  [README.md](README.md).
