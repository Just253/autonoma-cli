# Comandos y opciones

Referencia de la superficie de la CLI. Si cambiás un flag en `cli.py`, actualizá
este archivo: `tests/test_docs.py` verifica que cada comando exista acá y que
cada ejemplo del repo se pueda parsear.

## Tabla de comandos

| Comando | Qué hace |
|---------|----------|
| `autonoma login` | Inicia sesión y guarda las credenciales. |
| `autonoma logout` | Borra la cookie de sesión. Con `--credenciales` borra también el usuario y la contraseña. |
| `autonoma whoami` | Muestra la cuenta, el código de alumno y dónde viven las credenciales. |
| `autonoma credenciales` | Crea el archivo `credentials.txt` para editar usuario y contraseña a mano. |
| `autonoma cursos` | Lista los cursos del periodo (alias `ls`). |
| `autonoma curso CURSO` | Detalle del curso y su sílabo sesión por sesión. |
| `autonoma historial` | Cursos de todos los periodos, incluidos los cerrados. |
| `autonoma notas` | Notas por criterio, curso o periodo (`--todos`) y promedio oficial (`--promedio`). |
| `autonoma horario` | Horario de clases con fecha, hora y aula (alias `aula`). |
| `autonoma recursos CURSO` | Recursos de todas las sesiones (o de `--sesion N`). |
| `autonoma descargar CURSO` | Descarga los archivos del curso (alias `download`). |
| `autonoma todo` | Descarga los archivos de todos los cursos (alias `all`). |
| `autonoma cache` | Ver o borrar la caché local (`--borrar`). |

`CURSO` acepta el **índice** de `autonoma cursos`, el **nGruCodigo** o **parte
del nombre**:

```powershell
autonoma recursos 1
autonoma curso 90000001
autonoma descargar ejemplo
```

Los cursos de periodos cerrados se resuelven solos: si el token no está en el
catálogo actual, se busca en el historial.

## Opciones globales

Valen antes o después del comando: `autonoma --json cursos` y
`autonoma cursos --json` son equivalentes.

| Opción | Efecto |
|--------|--------|
| `--base-url URL` | Otro dominio del campus. |
| `--timeout SEG` | Timeout por petición. |
| `--delay SEG` | Pausa entre peticiones (0.5 por defecto). |
| `--out CARPETA` | Destino de las descargas (`./descargas` por defecto). Solo `descargar` y `todo`. |
| `--json` | Salida JSON (ver [JSON.md](JSON.md)). |
| `--refresh` | Ignora la caché de cursos, horario e historial. |
| `--no-color` | Sin ANSI, útil al capturar salida. |
| `-v`, `--verbose` | Más detalle. |
| `--version` | Versión instalada. |

## Opciones por comando

### `login`

| Opción | Efecto |
|--------|--------|
| `--usuario USUARIO` | Usuario del campus. |
| `-p`, `--password CLAVE` | Contraseña; si se omite se pide sin mostrarla. |
| `--no-guardar` | No guarda las credenciales. |

### `logout`

| Opción | Efecto |
|--------|--------|
| `--credenciales` | Borra también el usuario y la contraseña guardados. |

### `credenciales`

| Opción | Efecto |
|--------|--------|
| `--abrir` | Abre `credentials.txt` con el editor del sistema. |
| `--borrar` | Borra `credentials.txt`. |

### `cursos`

| Opción | Efecto |
|--------|--------|
| `--ciclo N` | Solo los cursos de ese ciclo. |
| `--periodo AAAA0S` | Solo los cursos de ese periodo (`209901`). |
| `--carrera TEXTO` | Solo cursos cuya carrera contenga el texto, sin acentos ni mayúsculas. |
| `--activos` | Solo los cursos activos (`EstadoCurso = 1`). |

### `historial`

| Opción | Efecto |
|--------|--------|
| `--ciclo N` | Solo los cursos de ese ciclo. |
| `--periodo AAAA0S` | Solo los cursos de ese periodo. |
| `--carrera TEXTO` | Filtra por carrera. |
| `--curso TEXTO` | Filtra por nombre o `nGruCodigo`. |

### `notas`

| Opción | Efecto |
|--------|--------|
| `CURSO` | Posicional opcional: detalle por criterio de ese curso. |
| `--todos` | Añade los periodos cerrados con su nota final (`nPromocional`). |
| `--promedio` | Añade el promedio oficial del tablero, por créditos y por ciclo. |
| `--ciclo`, `--periodo`, `--carrera` | Igual que en `cursos`. |
| `--activos` | Solo afecta la resolución de `CURSO`: el resumen ya muestra únicamente activos. |

Sin `CURSO` y sin `--todos` muestra solo los cursos activos, con el acumulado
del periodo y el porcentaje evaluado. El detalle por criterio necesita un curso
del periodo abierto; si el curso es de un periodo cerrado no hay criterios y
muestra su nota final del historial. `--promedio` se puede combinar con `CURSO`
y con `--todos`.

```powershell
autonoma notas
autonoma notas 1
autonoma notas 90000001 --json
autonoma notas --todos
autonoma notas --promedio
autonoma notas 1 --promedio --json
```

### `horario`

| Opción | Efecto |
|--------|--------|
| `CURSO` | Posicional opcional: limita a un curso. |
| `--hoy` | Solo las clases de hoy. |
| `--manana` | Solo las de mañana. |
| `--dia DD/MM/AAAA` | Un día concreto (acepta `hoy`, `manana`, `ayer`). |
| `--desde`, `--hasta` | Rango de fechas. |
| `--todo` | Todo el periodo. |
| `--ciclo`, `--periodo`, `--carrera`, `--activos` | Igual que en `cursos`. |

Sin opciones muestra los próximos 7 días.

### `recursos`

| Opción | Efecto |
|--------|--------|
| `-s`, `--sesion N` | Solo esa sesión (repetible). |

### `descargar` y `todo`

| Opción | Efecto |
|--------|--------|
| `-s`, `--sesion N` | Solo esa sesión (repetible). |
| `-t`, `--tipo TIPO` | `archivo` (por defecto), `tarea`, `evaluacion`, `foro`, `scorm` o `todo`. |
| `--solo REGEX` | Filtra por título, sin distinguir mayúsculas. |
| `--incluir-silabo` | Añade el PDF del sílabo. |
| `--seco`, `--dry-run` | Muestra el plan y no descarga. |
| `-w`, `--workers N` | Descargas en paralelo (4 por defecto). |
| `--forzar` | Vuelve a bajar aunque exista. |
| `--out CARPETA` | Destino. |

`todo` acepta además `--curso TEXTO` y los filtros de `cursos`.

### `cache`

| Opción | Efecto |
|--------|--------|
| `--borrar` | Borra los archivos de caché. |

## Códigos de salida

| Código | Significado |
|--------|-------------|
| `0` | Correcto. |
| `1` | Error genérico de la CLI. |
| `2` | Error de uso (argumentos o filtros). |
| `3` | Login rechazado. |
| `4` | Error del campus o de red. |
| `130` | Cancelado con Ctrl+C. |
