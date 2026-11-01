# autonoma-cli

CLI para **ver los cursos** y **descargar los archivos** del Campus Virtual de la
Universidad Autónoma del Perú desde la terminal. Sin navegador, sin clics y sin
dependencias externas: solo Python.

- Lista tus cursos con docente, grupo, ciclo, periodo, estado y cantidad de
  recursos, y distingue los de periodos anteriores.
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

#  Curso                      Codigo      Grupo  Ciclo  Periodo  Estado  Docente          Rec.
-  -------------------------  ----------  -----  -----  -------  ------  ---------------  ----
1  CURSO DE EJEMPLO UNO       PISOP00001  1A1-A      1   209901  activo  DOCENTE EJEMPLO    12
2  CURSO DE EJEMPLO DOS       PISOP00002  1A1-A      1   209901  activo  DOCENTE EJEMPLO     8
```

Y para comprobar la sesión y de dónde salieron las credenciales:

```powershell
autonoma whoami
```

## Documentación

| Documento | Contenido |
|-----------|-----------|
| [docs/CLI.md](docs/CLI.md) | Todos los comandos, flags, alias y códigos de salida. |
| [docs/GUIA.md](docs/GUIA.md) | Recorridos: elegir curso, horario, recursos, descargas, historial. |
| [docs/CONFIG.md](docs/CONFIG.md) | Credenciales, variables de entorno, `settings.json`, caché y rutas. |
| [docs/JSON.md](docs/JSON.md) | Forma de la salida `--json` y nombres de campos. |
| [docs/API.md](docs/API.md) | Contrato interno del campus (endpoints, campos y trampas). |
| [docs/DESARROLLO.md](docs/DESARROLLO.md) | Arquitectura, guardia, tests y cómo agregar un comando. |

## Limitaciones

- Depende de endpoints internos no documentados: si el campus los cambia, habrá
  que ajustar `client.py`.
- No soporta CAPTCHA ni MFA (hoy el login no los pide).
- No descarga el contenido de tareas, foros ni evaluaciones: solo archivos
  publicados con URL.
- El historial no consulta periodos que el campus no devuelva.
- Respeta el ritmo del servidor (`--delay`, 0.5 s por defecto). No lo bajes sin
  motivo.
