# AGENTS.md

CLI en Python (solo stdlib) para el Campus Virtual de la Universidad Autónoma
del Perú. Este archivo es para agentes que trabajen en el repo.

## Antes de tocar nada

```powershell
py -3.12 -m pytest -q
py -3.11 -m unittest discover -s tests
```

`tests/test_architecture.py` fija la estructura (tamaños, imports, quién
imprime). `tests/test_docs.py` ejecuta los ejemplos de los Markdown. Si rompés
alguno de los dos, el problema es tu cambio, no el test.

## Dónde se documenta cada cosa

El mapa completo está en [docs/README.md](docs/README.md). Resumen:

| Dato | Archivo |
|------|---------|
| Comandos, flags, códigos de salida | `docs/CLI.md` |
| Recorridos por tarea y ejemplos de uso | `docs/GUIA.md` |
| Credenciales, variables, `settings.json`, caché | `docs/CONFIG.md` |
| Esquema de `--json` | `docs/JSON.md` |
| Endpoints y campos del campus | `docs/API.md` |
| Arquitectura, tests, cómo agregar un comando | `docs/DESARROLLO.md` |

**Regla: un dato, un lugar.** No copies tablas de flags ni esquemas JSON en el
README ni en la skill; enlazá.

## Reglas duras

- **Nunca datos reales** en tests, ejemplos ni docs: ni `nGruCodigo`, ni
  docentes, ni aulas, ni carreras, ni periodos de la cuenta. Usá los ficticios
  (`90000001`, `209901`, `DOCENTE DE EJEMPLO`).
- **Nunca** leer ni imprimir credenciales, cookies ni `session.cookies`.
- `cli.py` ≤ 260 líneas; `commands/*.py` ≤ 120; `config/*.py` ≤ 200.
- Un comando por archivo en `commands/`, `run_*(client, args)` y reexport en
  `commands/__init__.py`.
- `cli.py` y `commands/` no imprimen: usan `render` o `ui`.
- Mensajes de commit en ASCII, imperativo, con el porqué en el cuerpo.

## Mapa rápido del código

`cli.py` (parser) → `commands/` (un módulo por tema) → `cache`, `render`,
`selectors`, `client`, `downloader` → `config`, `models`, `errors`, `ui`.
Detalle en [docs/DESARROLLO.md](docs/DESARROLLO.md).

La skill global `autonoma-campus` vive fuera del repo
(`~/.config/opencode/skills/`); si cambia un flujo de uso, conviene actualizarla
también, sin duplicar la referencia de flags.
