# autonoma-cli

CLI para **ver los cursos** y **descargar los archivos** del Campus Virtual de la
Universidad Autónoma del Perú desde la terminal. Sin navegador, sin clics y sin
dependencias externas: solo Python.

- Lista tus cursos del periodo con docente, grupo, ciclo y cantidad de recursos.
- Muestra el sílabo de cada curso (sesiones, semanas, temas y logros).
- Muestra el horario de cada sesión: fecha, hora, modalidad y **aula**.
- Lista los recursos de cada sesión (archivos, tareas, evaluaciones, foros, SCORM).
- Descarga los archivos a una estructura ordenada por curso y sesión, con
  reanudación por manifiesto y verificación sha256.
- Guarda tus credenciales de forma cifrada para no escribirlas en cada comando.

> Proyecto personal. Usa solo tu propia cuenta y con una cadencia razonable.
> El material descargado es del docente y de la universidad: su reutilización
> está sujeta a sus políticas.

---

## Requisitos

- Python 3.10 o superior.
- Windows, Linux o macOS.
- Nada más: el cliente HTTP, el manejo de cookies y las tablas son de la
  biblioteca estándar.

## Instalación

```powershell
git clone https://github.com/Just253/autonoma-cli.git
cd autonoma-cli
pip install -e .
```

Comprueba que quedó instalado:

```powershell
autonoma --version
```

También funciona sin instalar, desde la carpeta del repo:

```powershell
python -m autonoma_cli --help
```

## Primer uso

```powershell
autonoma login
```

Pide usuario y contraseña (la contraseña no se muestra), inicia sesión en el
campus y guarda las credenciales. Después:

```powershell
autonoma cursos
```

```
2 cursos · periodo 209901

#   Curso                          Codigo       Grupo  Ciclo  Docente                  Rec.
--  -----------------------------  -----------  -----  -----  -----------------------  ----
1   CURSO DE EJEMPLO UNO           PISOP00001   1A1-A      1  DOCENTE DE EJEMPLO        12
2   CURSO DE EJEMPLO DOS           PISOP00002   1A1-A      1  DOCENTE DE EJEMPLO         8
```

## Comandos

| Comando | Qué hace |
|---------|----------|
| `autonoma login` | Inicia sesión y guarda las credenciales. |
| `autonoma logout` | Borra la cookie de sesión. Con `--credenciales` borra también el usuario y la contraseña. |
| `autonoma whoami` | Muestra la cuenta, el código de alumno y dónde viven las credenciales. |
| `autonoma credenciales` | Crea el archivo `credentials.txt` para editar usuario y contraseña a mano. |
| `autonoma cursos` | Lista los cursos del periodo (alias `ls`). |
| `autonoma curso CURSO` | Detalle del curso y su sílabo sesión por sesión. |
| `autonoma horario` | Horario de clases con fecha, hora y aula (alias `aula`). |
| `autonoma recursos CURSO` | Recursos de todas las sesiones (o de `--sesion N`). |
| `autonoma descargar CURSO` | Descarga los archivos del curso. |
| `autonoma todo` | Descarga los archivos de todos los cursos. |
| `autonoma cache` | Ver o borrar la caché local (`--borrar`). |

`CURSO` acepta el **índice** de `autonoma cursos`, el **nGruCodigo** o **parte
del nombre**:

```powershell
autonoma recursos 1
autonoma curso 90000001
autonoma descargar ejemplo
```

### Horario y aulas

```powershell
# Qué clase y en qué aula te toca hoy
autonoma horario --hoy

# Próximos 7 días (sin opciones)
autonoma horario

# Un día concreto, un rango o todo el periodo
autonoma horario --dia 15/03/2099
autonoma horario --desde 01/11/2026 --hasta 15/11/2026
autonoma horario --todo

# Solo un curso (índice, nGruCodigo o parte del nombre)
autonoma horario ejemplo --todo
```

```
Hoy, 15/03/2099 · 1 sesion

Martes 15/03/2099
Hora         Curso                                           Aula                            Tipo        Ses.
-----------  ----------------------------------------------  ------------------------------  ----------  ----
19:30-22:30  CURSO DE EJEMPLO UNO  A-101 (Laboratorio de Ejemplo)  Presencial  08

  08 · Tema de ejemplo de la sesion.
```

- `Aula` es el campo `ambiente` del campus: el aula física o `Sala zoom` en
  las sesiones virtuales.
- `Tipo` distingue `Presencial`, `Sincrona` y `Asincrona`.
- Solo entran los cursos activos del periodo. Para mirar uno ya terminado,
  nómbralo: `autonoma horario "ejemplo" --todo`.
- La programación se guarda 6 horas en la caché (`cache.json`, junto con los
  cursos); usa `--refresh` para forzarla. `--json` devuelve las mismas sesiones
  para scripts.

### Filtrar recursos

```powershell
# Solo una sesión
autonoma recursos 1 --sesion 4

# Solo archivos PDF cuyo título mencione "presentacion"
autonoma descargar 1 --solo "presentacion"

# Tareas y evaluaciones (no solo archivos)
autonoma descargar 1 --tipo tarea
autonoma descargar 1 --tipo evaluacion

# Ver el plan sin descargar nada
autonoma descargar 1 --seco
```

Tipos disponibles: `archivo` (por defecto), `tarea`, `evaluacion`, `foro`,
`scorm` y `todo`.

### Descargar

```powershell
autonoma descargar 1
```

```
CURSO DE EJEMPLO UNO
  PISOP00001 · periodo 209901 · ciclo 1 · grupo 1A1-A · 4 creditos · VIRTUAL
  Docente: DOCENTE DE EJEMPLO <docente@ejemplo.edu.pe>
  nGruCodigo: 90000001 · recursos: 12

Descargando 2 archivos → ./descargas
  [ok]    S01 · PRESENTACION: TEMA DE EJEMPLO (3.4 MB)
  [igual] S01 · LECTURA: OTRO TEMA DE EJEMPLO
  [ok]    S02 · PRESENTACION: TEMA DE EJEMPLO DOS (5.1 MB)

Descargados: 2 · Ya estaban: 1 · Errores: 0 · Total: 8.5 MB
```

Opciones útiles:

| Opción | Efecto |
|--------|--------|
| `--out CARPETA` | Cambia el destino (por defecto `./descargas`). |
| `--sesion N` | Limita a una o varias sesiones (repetible). |
| `--solo REGEX` | Filtra por título. |
| `--seco` | Muestra el plan y no descarga. |
| `--workers N` | Descargas en paralelo (por defecto 4). |
| `--forzar` | Vuelve a bajar aunque el archivo exista. |
| `--incluir-silabo` | Añade el PDF del sílabo del curso. |

### Estructura de las descargas

```
descargas/
├── manifest.json                       # url → archivo, bytes, sha256
└── CURSO_DE_EJEMPLO_UNO/
    ├── Sesion_01/
    │   ├── ARCHIVO_PRESENTACION_TEMA_UNO.pdf
    │   └── ARCHIVO_LECTURA_TEMA_UNO.pdf
    └── Sesion_02/
        └── ARCHIVO_PRESENTACION_TEMA_DOS.pdf
```

- El nombre sale del título del recurso, sin acentos ni caracteres inválidos.
- Cada descarga se escribe como `.part` y se renombra al terminar: no quedan
  archivos a medias.
- `manifest.json` guarda el tamaño y el sha256. Si el archivo existe con el
  mismo tamaño, se omite.
- `--json` da la misma información en JSON para scripts.

## Credenciales y sesión

- Se guardan en el directorio de configuración del usuario, **nunca en el repo**:
  - Windows: `%APPDATA%\autonoma-cli\credentials.json`
  - Linux/macOS: `~/.config/autonoma-cli/credentials.json`
- En Windows la contraseña se cifra con **DPAPI** (`CryptProtectData`): solo tu
  usuario de Windows puede descifrarla. Ni el archivo ni el repo contienen la
  contraseña en claro.
- En Linux/macOS se guarda con permisos `0600` y se avisa en el primer guardado.
- La cookie de sesión vive en `session.cookies`, en la misma carpeta. Se reutiliza
  mientras no expire; si el campus la invalida, la CLI vuelve a iniciar sesión con
  las credenciales guardadas.
- Para no guardar nada: `autonoma login --no-guardar`, o usa las variables
  `AUTONOMA_USER` y `AUTONOMA_PASSWORD` (tienen prioridad sobre el archivo).
- Para borrar todo: `autonoma logout --credenciales`.

Evita `--password` en la terminal: queda en el historial. Escribe la contraseña
cuando la CLI la pida (no se muestra en pantalla).

### Archivo editable a mano (`credentials.txt`)

Si prefieres ver y editar tus credenciales como texto:

```powershell
autonoma credenciales
```

Crea (si no existe) y muestra este archivo:

```
%APPDATA%\autonoma-cli\credentials.txt
```

```ini
# Credenciales del Campus Virtual - autonoma-cli
usuario=
password=
```

Completa las dos líneas y guarda. La CLI lo lee en cada comando y **tiene
prioridad** sobre las credenciales cifradas que guarda `autonoma login`.

- Alias aceptados: `usuario`, `user`, `username`, `correo` para el usuario;
  `password`, `pass`, `clave`, `contrasena`, `contraseña` para la contraseña.
- El separador puede ser `=` o `:`; las comillas alrededor del valor se ignoran.
- Las líneas que empiezan con `#` o `;` son comentarios.
- Si el archivo está vacío o incompleto, se usan las credenciales cifradas.
- Para abrirlo con el editor del sistema: `autonoma credenciales --abrir`.
- Para volver al cifrado: `autonoma credenciales --borrar` y luego `autonoma login`.

El archivo está en texto plano: no lo compartas ni lo subas a un repo
(`.gitignore` ya excluye `credentials.txt`). En Linux/macOS se crea con
permisos `0600`.

Verifica dónde quedó todo:

```powershell
autonoma whoami
```

## Variables de entorno

| Variable | Efecto |
|----------|--------|
| `AUTONOMA_USER` / `AUTONOMA_PASSWORD` | Credenciales sin tocar disco. |
| `AUTONOMA_BASE_URL` | Otro dominio del campus. |
| `AUTONOMA_CLI_HOME` | Otra carpeta de configuración (pruebas). |
| `AUTONOMA_OUT` | Carpeta de descargas por defecto. |
| `AUTONOMA_DELAY` | Pausa entre peticiones (segundos). |
| `NO_COLOR` | Desactiva color. |

## Cómo funciona

El campus es ASP.NET Web Forms con un frontend React. El login es un POST de
formulario con `__VIEWSTATE` y `__EVENTVALIDATION`; los datos salen de
*WebMethods* JSON en `/Campus/Default.aspx/<metodo>`, y los archivos viven en
`/uploads/<nombre>`. Los detalles del contrato interno, los campos y las
trampas están en [`docs/API.md`](docs/API.md).

```
autonoma_cli/
├── __init__.py         # versión del paquete
├── __main__.py         # python -m autonoma_cli
├── cli.py              # parser de argumentos y despacho
├── commands/           # un módulo por comando: run_*(client, args)
│   ├── __init__.py     # reexporta los run_* que usan cli.py y los tests
│   ├── base.py         # cliente, carpeta de salida y reportes compartidos
│   ├── data.py         # cursos, horario y recursos con caché
│   ├── account.py      # login, logout y whoami
│   ├── courses.py      # cursos y curso
│   ├── credenciales.py # credenciales: archivo editable a mano
│   ├── download.py     # descargar y todo
│   ├── maintenance.py  # cache
│   ├── resources.py    # recursos de un curso
│   └── timetable.py    # horario: fechas, horas y aulas
├── config/             # credenciales, cookies y preferencias
│   ├── __init__.py     # reexporta la API pública de configuración
│   ├── paths.py        # rutas, constantes y carpeta del usuario
│   ├── io.py           # escritura atómica de archivos privados (0600)
│   ├── crypto.py       # cifrado DPAPI (solo Windows)
│   ├── credentials.py  # guardar y leer credenciales (cifradas o en claro)
│   ├── plain.py        # credentials.txt editable a mano
│   └── settings.py     # settings.json y variables de entorno
├── client.py           # login ASP.NET, cookies y WebMethods
├── models.py           # Course / SessionTopic / ClassSession / Resource normalizados
├── downloader.py       # plan, descarga atómica, manifiesto y sha256
├── cache.py            # caché de cursos y horario en un único cache.json
├── render.py           # tablas, cabeceras y salida JSON
├── selectors.py        # filtros de curso, sesión, tipo y fechas
├── ui.py               # tablas y color
└── errors.py           # errores tipados
```

## Desarrollo

```powershell
python -m unittest discover -s tests -v
```

Los tests no tocan la red: cubren parseo del formulario, normalización de
respuestas, rutas de descarga, manifiesto y credenciales (con `AUTONOMA_CLI_HOME`
temporal).

## Limitaciones

- Depende de endpoints internos no documentados: si el campus los cambia, habrá
  que ajustar `client.py`.
- No soporta CAPTCHA ni MFA (hoy el login no los pide).
- No descarga el contenido de tareas, foros ni evaluaciones: solo archivos
  publicados con URL.
- Respeta el ritmo del servidor (`--delay`, 0.5 s por defecto). No lo bajes sin
  motivo.
