# Desarrollo

## Cómo encaja todo

```
cli.py  →  commands/  →  cache.py, render/, selectors.py, client.py, files/
                 ↓                              ↓
              config/, models/, ui.py, errors.py    api/, auth/, session.py, net.py
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
│   └── …               # account, courses, history, timetable, resources, grades, download, entregar, maintenance, credenciales
├── config/             # rutas, io atómico, DPAPI, credenciales, settings
├── client.py           # fachada: constructor, delegaciones y describe
├── api/                # política de llamadas, WebMethods y desempaquetado
├── session.py          # transporte HTTP: opener, jar, pin de IP y pausa
├── auth/               # login, cookies y código de alumno
├── net.py              # pin de IP, TLS y resolución del campus
├── models/             # un dominio por archivo: common, courses, resources, sessions, grades, uploads
├── files/              # plan, manifiesto, descarga atómica y corrida
├── uploader.py         # plan y corrida de una subida (una subida y un registro)
├── uploadcheck.py      # valida archivo y textos antes de tocar la red
├── uploadform.py       # contrato del campus: multipart, XML y respuestas
├── cache.py            # cache.json (cursos, horario, historial)
├── render/             # un tema por archivo: text, courses, schedule, resources, downloads, grades, upload
├── selectors.py        # filtros de curso, sesión, tipo y fechas
├── ui.py               # tablas y color
└── errors.py           # errores tipados
```

`client.py` no sabe de formularios, cookies ni reintentos: el login y el jar
viven en `auth/`, la política de llamadas y los WebMethods en `api/`, el opener y
el pin en `session.py`, y `net.py` resuelve y valida el certificado. Los comandos
solo ven el cliente.

## La guardia de arquitectura

`tests/test_architecture.py` no prueba comportamiento: fija dónde vive cada
cosa. Si algo falla, el mensaje dice qué hacer. Reglas principales:

- `cli.py` ≤ 260 líneas, cada `commands/*.py` ≤ 120, cada `config/*.py` ≤ 200,
  `models/*.py` ≤ 250, `render/*.py` ≤ 200, `uploadcheck.py` ≤ 120,
  `uploader.py` ≤ 260, `uploadform.py` ≤ 200 y `tests/test_*.py` ≤ 300 (salvo
  `test_architecture.py`).
- `cli.py` y `commands/` no imprimen: usan `render` o `ui`.
- JSON a mano solo en el módulo dueño del archivo; el resto pasa por
  `cache.ensure` o `render.emit_json`:

  | Archivo | Dueño |
  |---------|-------|
  | `cache.json` | `cache.py` |
  | `manifest.json` | `files/manifest.py` |
  | `pinned-ip.json` | `net.py` |
  | `settings.json` y credenciales | `config/` |
  | respuesta `{"d": ...}` | `api/json.py` |
  | salida `--json` | `render/text.py` |
- El multipart y el XML de la subida se arman solo en `uploadform.py`;
  `uploadcheck.py` valida archivo y textos antes de la red y `uploader.py` hace
  el plan y la corrida.
- `strip_html` se define solo en `models/common.py`; `write_private_text`, en
  `config/io.py`.
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
