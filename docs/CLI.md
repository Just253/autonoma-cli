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
| `autonoma entregar GRUPO ARCHIVO` | Sube un archivo a una carpeta compartida o a una tarea (con `--seco` y `--confirmar`). |
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
| `--refresh` | Ignora la caché de cursos, horario, historial y recursos. |
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

### `entregar`

Es el único comando que escribe en el campus. Un archivo por corrida, sin
borrado ni edición.

| Opción | Efecto |
|--------|--------|
| `GRUPO` | Curso: índice de `autonoma cursos`, `nGruCodigo` o parte del nombre. |
| `ARCHIVO` | Archivo a subir. |
| `--carpeta N` | Destino: carpeta compartida (`nDocLinNum`). |
| `--tarea N` | Destino: tarea (`nDocLinNum`). |
| `--titulo TEXTO` | Obligatorio: nombre visible del recurso. |
| `--descripcion TEXTO` | Obligatoria: el campus la pide al registrar. |
| `--param0 TEXTO` | Solo tareas: nombre base del archivo. Sin esto se conserva el original. |
| `--sesion N` | Solo `--carpeta`: semana donde vive la carpeta. Salta la búsqueda y sus lecturas. |
| `--seco`, `--dry-run` | Muestra el plan y sale sin subir nada. |
| `--confirmar` | Obligatorio para subir de verdad. |

Exactamente uno de `--carpeta` / `--tarea`. Sin `--seco` y sin `--confirmar` la
CLI no pregunta: sale con error de uso (código 2). `--seco` y `--confirmar`
juntos también son error de uso. Una carpeta compartida solo acepta `pdf`, `rar`
o `zip`; avisa si el archivo pasa de 5 MB, pero sube hasta 25 MB. Si el campus
rechaza el registro, muestra el motivo, sale con código 4 y no reintenta ni
prueba el otro destino.

Sin `--sesion`, `--carpeta` mira primero la sesión activa (1 lectura) y, si la
carpeta no está ahí, recorre las sesiones de a una hasta encontrarla. Un archivo
inválido o un `--param0` con `--carpeta` fallan antes de pedir el catálogo.

```powershell
autonoma entregar 1 entrega.zip --tarea 209901 --titulo "ENTREGA DE EJEMPLO" --descripcion "Trabajo de ejemplo" --seco
```

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
