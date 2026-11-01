# API interna del Campus Virtual (no documentada)

Este documento resume el contrato que usa `autonoma-cli`. Sale de inspeccionar
el propio campus: el frontend React montado sobre ASP.NET
Web Forms más los bundles `CCamp_Virt_Est_Curso.js`, `Camp_Virt_Principal.min.js`
y `reactBridge.js`.

> Cambia sin aviso. Si un método deja de responder, empieza por aquí.

## 1. Login

```
GET  /Campus/Login.aspx
POST /Campus/Login.aspx
```

El formulario `#frmLogin` es un postback clásico. Campos:

| Campo | Origen |
|-------|--------|
| `__EVENTTARGET`, `__EVENTARGUMENT`, `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION` | ocultos del HTML |
| `txtUsuario` | usuario |
| `txtPassword` | contraseña |
| `btn_ingresar` | `Ingresar` |

Detalles que rompen implementaciones ingenuas:

- Los `<input>` repiten el atributo `name`
  (`name="txtUsuario" … name="email-username"`). Un `dict(attrs)` se queda con
  el **último**; hay que quedarse con el **primero**.
- El login correcto redirige a `/Campus/Default.aspx` y deja el código de alumno
  en `id="cPerCodigo"` (también en `txtcPerCodigoLog`).
- El login fallido vuelve a `Login.aspx` y escribe el motivo en
  `<span id="FailureText">`.
- La sesión es una cookie `ASP.NET_SessionId`; reutilizarla evita el POST.

## 2. WebMethods

Patrón general:

```
POST /Campus/Default.aspx/<metodo>
Content-Type: application/json; charset=utf-8
X-Requested-With: XMLHttpRequest
Referer: /Campus/Default.aspx

{ ...payload... }
```

Respuesta: `{"d": ...}`. En varios métodos `d` es **un string JSON** que hay que
decodificar otra vez.

| Método | Payload | Devuelve |
|--------|---------|----------|
| `Alu_ObtenerCursosActuales` | `{}` | lista de cursos |
| `getInformationDetailCurso` | `{nGruCodigo, nSesion, nPerfil: 13}` | ver abajo |
| `getNotasAlumnoGrupo` | `{nGruCodigo}` | notas del curso |
| `getProgramacionAlumnoGrupo` | `{nGruCodigo}` | horario: fechas, horas y aula |

`nPerfil: 13` es el perfil de alumno; el campus lo calcula con
`CampVirtSecurity.getPerfil()` y en estudiantes siempre es 13.

### `getInformationDetailCurso`

| `nSesion` | Respuesta |
|-----------|-----------|
| `0` | objeto `{silabo, recursos, rutaAprendizaje, cUrlVideoPresentacion, cGuiaAprendizaje, …}`. `recursos` son los de la **sesión activa**. |
| `>= 1` | **lista** de recursos de esa sesión. |

`silabo` es la lista completa de sesiones:

```json
{
  "nSesion": 1, "cSesion": "01",
  "semana_fecha_inicio": "01/03/2027", "semana_fecha_fin": "07/03/2027",
  "tema": "Tema de ejemplo…",
  "logro": "Al finalizar la sesión…",
  "sesion_activa": 0
}
```

### `getProgramacionAlumnoGrupo`

Devuelve una lista con una entrada por sesión programada:

```json
{
  "nSesion": 8, "sesion": 8,
  "tema": "Tema de ejemplo de la sesión…",
  "fecha": "15/03/2099 19:30 a 22:30",
  "fechaParse": 4077286200000,
  "nHorCodigo": 12345678,
  "tipo": "<span class=\"badge bg-label-secondary\">Presencial</span>",
  "nTipo": 2,
  "ambiente": "A-101 (Laboratorio de Ejemplo)",
  "nGrabacion": 0
}
```

| Campo | Uso |
|-------|-----|
| `tema` | tema de la sesión (multilínea: la primera línea es el título) |
| `fecha` | fecha y rango horario en texto: `dd/mm/aaaa HH:MM a HH:MM` |
| `fechaParse` | la fecha en milisegundos epoch (UTC), como respaldo |
| `nTipo` | `0` síncrona, `1` asíncrona, `2` presencial |
| `tipo` | el mismo dato como HTML con `badge`; hay que quitar las etiquetas |
| `ambiente` | **aula** (`A-101 (Laboratorio de Ejemplo)`) o `Sala zoom` |
| `nGrabacion` | `1` si la sesión quedó grabada |
| `nHorCodigo` | identificador del bloque de horario |

La respuesta no trae el curso: hay que pedirla por `nGruCodigo`. Algunas
sesiones aparecen repetidas o faltan (huecos de la programación del campus).

## 3. Campos de un curso

| Campo | Uso |
|-------|-----|
| `nGruCodigo` | id del grupo matriculado (la llave para todo) |
| `asignatura` | nombre visible |
| `codigo` / `cCurDetCod` | código del curso |
| `periodo`, `ciclo`, `seccion`, `grupo` | ubicación académica |
| `creditos`, `modalidad` | datos del curso |
| `docenteNombre` + `docenteApellido`, `correoDocente` | docente |
| `fechaInicioCurso`, `fechaFinCurso` | fechas (dd/mm/yyyy) |
| `cantidadRecursos` | total de recursos |
| `EstadoCurso` | `1` = activo |
| `cSilabo` | ruta del PDF del sílabo (`/UploadsEnvioEmailPDF/…`) |

## 4. Campos de un recurso

```json
{
  "cTitulo": "PRESENTACIÓN: TEMA DE EJEMPLO",
  "nDocLinTipo": 2,
  "nDocLinNum": 3,
  "nSesion": 1,
  "cSesion": "01",
  "url": "01-03-2027_000000000_000DOCUMENTO.pdf",
  "clase": "far fa-file-pdf",
  "dDocTraFec": "01/03/2027",
  "nItinerario": 2
}
```

### Tipos (`nDocLinTipo`)

| Valor | Tipo |
|-------|------|
| 0 | Sílabo |
| 1 | Carpeta |
| 2 | Archivo (PDF, PPT, DOCX, ZIP…) |
| 3 | Enlace |
| 4 | Tarea |
| 5 | Evaluación |
| 6 | Cuestionario |
| 7 | Foro |
| 8 | Wiki |
| 9 | Reunión |
| 10 | SCORM |

Solo los recursos con `url` tienen archivo. Las carpetas no.

### Ruta de aprendizaje (`nItinerario`)

| Valor | Momento |
|-------|---------|
| 1 | INDAGA |
| 2 | INTERIORIZA |
| 3 | INTEGRA |

## 5. Archivos

```
GET /uploads/<url>
```

- `url` es relativa a `/uploads/`.
- Algunos campos traen sufijos `||…` que hay que descartar.
- `cSilabo` viene como ruta absoluta al dominio (`/UploadsEnvioEmailPDF/…`), no
  como nombre relativo.
- Requiere la cookie de sesión: sin ella redirige al login.
- La extensión real puede deducirse de `clase` (`far fa-file-pdf` → `.pdf`)
  cuando la URL no la trae.

## 6. Trampas conocidas

- **Errata del campus:** la sesión 06 de algunos cursos titula su presentación
  `PRESEMTACIÓN` (con M). Un filtro `PRESENTACIÓN` estricto la pierde; usa
  `PRESE\w?TAC` o el tipo de recurso.
- El listado de cursos trae `cantidadRecursos` de todo el curso, no de la sesión.
- El nombre del archivo original no es único entre sesiones: usa la sesión en la
  ruta para evitar colisiones.
- El orden de los recursos no es el orden de `orden`: ordena por `nItinerario` y
  luego por `orden` si necesitas la secuencia pedagógica.
- Los WebMethods pueden devolver `d` como string JSON o como objeto: normaliza
  siempre.

## 7. Historial de cursos (otra app interna)

La página `/Campus/ua/MisCursos/HistorialCursos/Camp_Virt_HistCursos.aspx` (se
carga con un `POST` vacío dentro del contenedor de Mis Cursos) trae la tabla
vacía; los datos los piden dos WebMethods que viven en otras rutas:

| Método | Ruta | Payload | Devuelve |
|--------|------|---------|----------|
| `obtenerUniOrgCurriculo` | `/Modulos/Campus/MisCursos/Ca_Mc_CursosMatriculados.aspx` | `{cPerCodigo, nTipCur}` | currículas |
| `ObtenerCursosByCurricula` | `/CampusVirtual/ua/Alumno/MisCursos/Alu_HistorialCursos.aspx` | `{nCurCodigo, cPerCodigo, cTablas}` | `{HISTORIAL_CURSOS, PERIODO_HISTORIAL_CURSOS}` |

- `cPerCodigo` es el código de alumno que está en `<input id="cPerCodigo">` de
  `Default.aspx`. Sin él, `obtenerUniOrgCurriculo` devuelve `[]`.
- `nTipCur`: `1` carrera, `2` extraacadémicos (idiomas). `3` y `102` existen en
  el JS (posgrado y talleres) y suelen venir vacíos.
- `nCurCodigo` es la **currícula**, no la carrera: un alumno puede tener varias
  (la vigente y las antiguas) y los cursos viejos viven en las no vigentes. Hay
  que recorrerlas todas y deduplicar por `nGruCodigo`.
- `cTablas` pide las dos tablas juntas, separadas por coma.
- Las filas de `HISTORIAL_CURSOS` traen `cPeriodo`, `nCiclo`, `asignatura`,
  `cEstado` (`APROBADA`, `EN PROCESO`, …), `cTipo`, `docente` y `nGruCodigo`.
- Las rutas `/CampusVirtual` y `/Modulos` comparten la cookie de `/Campus`.
- Los `nGruCodigo` del historial siguen respondiendo a
  `getInformationDetailCurso`: sílabo y recursos de periodos cerrados se pueden
  consultar y descargar.
