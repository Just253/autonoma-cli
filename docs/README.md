# Documentación

Índice y reglas. **Cada dato tiene un solo lugar**: si algo ya está escrito en
otro archivo, se enlaza, no se copia.

| Si vas a documentar… | Va en |
|----------------------|-------|
| Qué es la CLI, requisitos, instalación, primer uso | [README](../README.md) |
| Un comando, un flag, un alias, un código de salida | [CLI.md](CLI.md) |
| Un recorrido por tarea (elegir curso, horario, descargar, historial) | [GUIA.md](GUIA.md) |
| Credenciales, variables de entorno, `settings.json`, caché, rutas | [CONFIG.md](CONFIG.md) |
| Forma de la salida `--json` y nombres de campos | [JSON.md](JSON.md) |
| Endpoints, payloads, campos y trampas del campus | [API.md](API.md) |
| Arquitectura, guardia, tests, cómo agregar un comando, convenciones | [DESARROLLO.md](DESARROLLO.md) |

## Reglas

1. **Un dato, un lugar.** La tabla de flags vive solo en `CLI.md`; el esquema
   JSON solo en `JSON.md`; las rutas y variables solo en `CONFIG.md`. El resto
   enlaza.
2. **La verdad ejecutable manda.** `autonoma <comando> --help` sale del parser.
   Si el parser y `CLI.md` difieren, el bug es de la documentación (o del parser,
   pero hay que decidirlo).
3. **Los ejemplos se ejecutan.** `tests/test_docs.py` parsea cada línea
   `autonoma …` de los Markdown; un flag inventado rompe el test.
4. **Nada de datos reales.** Grupos, docentes, aulas, carreras, periodos y fechas
   de ejemplo son ficticios.
5. **El README no es la referencia.** Presenta el proyecto y enlaza; no repite
   comandos ni esquemas.
6. **La skill de agentes no es un segundo README.** Tiene el flujo, las trampas y
   las reglas de credenciales; para el detalle enlaza a estos archivos.

## Al cambiar algo

- ¿Nuevo flag o comando? `CLI.md` + `cli.py` + test de parser.
- ¿Nuevo formato de salida? `JSON.md` + test del comando.
- ¿Nueva ruta o variable? `CONFIG.md`.
- ¿Nuevo endpoint o campo del campus? `API.md` + `client.py`.
- ¿Cambia la estructura de módulos? `DESARROLLO.md`.
