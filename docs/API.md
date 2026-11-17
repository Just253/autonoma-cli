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
- Los archivos de `/uploads/` son **públicos**: no requieren la cookie de
  sesión (verificado el 2026-11-17 sobre documentos, PDFs y el sílabo). Lo que
  necesita cookie es la API que lista los recursos, no el archivo.
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

## 8. Notas y promedios

Hay cuatro fuentes distintas y **no son intercambiables**:

| Qué | De dónde |
|-----|----------|
| Criterios del periodo en curso | `getNotasAlumnoGrupo` |
| Nota final de un curso cerrado | `HISTORIAL_CURSOS.nPromocional` (§7) |
| Promedio acumulado y por ciclo | `Camp_Virt_Perfil.aspx/ObtenerDataAvanceCarrera` |
| Boleta del periodo abierto | `Alu_BoletaNotas.aspx/Alu_ObtenerBoletaNotas` |

### Periodo en curso: `getNotasAlumnoGrupo`

`POST /Campus/Default.aspx/getNotasAlumnoGrupo` con `{nGruCodigo}`:

```json
{
  "fechaActualizado": "02/11/2027 20:30:30",
  "nPromTotal": "9.6",
  "porcentaje": "67",
  "notas": [
    {"Criterio": "EC", "Peso": "10", "nota": "20.00", "nSesion": 4,
     "cFechaInicio": "25/09/2027", "cFechaFin": "27/09/2027"},
    {"Criterio": "EP", "Peso": "40", "nota": "19.00", "nSesion": 8,
     "cFechaInicio": "23/10/2027", "cFechaFin": "25/10/2027"},
    {"Criterio": "EF", "Peso": "50", "nota": "-", "nSesion": 16,
     "cFechaInicio": "18/12/2027", "cFechaFin": "19/12/2027"}
  ]
}
```

- `nPromTotal` **no es un promedio**: es la suma de `nota × Peso/100` de los
  criterios ya calificados (`20×0.10 + 19×0.40 = 9.6`). Mientras falte un
  criterio con peso alto el máximo alcanzable no es 20. Llamarlo "acumulado",
  nunca "promedio".
- `porcentaje` es el avance del curso, no la nota.
- Los `Peso` de los criterios suman 100 por curso.
- `nota` es texto con punto decimal (`"12.50"`) o `"-"` si no está calificada.
- `Criterio` viene como código corto (`EC`, `EP`, `EF`).
- Solo responde para grupos del periodo abierto. En un grupo de periodo cerrado
  devuelve `nPromTotal: "0"`, `porcentaje: "0"` y `notas: []`: no sirve como
  fuente histórica.

### Periodos cerrados: `nPromocional`

Cada fila de `HISTORIAL_CURSOS` (ver §7) trae `nPromocional`: la nota final del
curso en escala 0–20, como entero. No requiere ninguna petición extra.

- Las filas del periodo abierto también traen `nPromocional`, pero ahí es el
  acumulado parcial redondeado, no la nota final.
- `Nota` de la malla (abajo) también viene redondeada. El gráfico por ciclo usa
  decimales internos que la API no expone por curso, así que recalcular un ciclo
  puede diferir en centésimas.

### Boleta del periodo: `Alu_ObtenerBoletaNotas`

`POST /CampusVirtual/ua/Alumno/MisCursos/Alu_BoletaNotas.aspx/Alu_ObtenerBoletaNotas`
con `{cPerCodigo: "", cTablas: "Boleta_notas"}`:

- Devuelve `Boleta_notas`: una fila por curso del periodo con `CURSO`, `CRED`,
  `CICLO`, `Periodo`, `ESTADO`, `NOT1` (decimal exacto, igual a `nPromTotal`) y
  `PROMFINAL` (entero redondeado).
- Es la boleta que muestra el campus; `getNotasAlumnoGrupo` da el detalle por
  criterio.

### Promedio oficial: `ObtenerDataAvanceCarrera`

1. `POST /Campus/ua/Tablero/Perfil/Camp_Virt_Perfil.aspx/ObtenerCurrriculasActuales`
   con `{cPerCodigo}` → cada currícula trae `nPerAluRegCodigo`.
2. `POST /Campus/ua/Tablero/Perfil/Camp_Virt_Perfil.aspx/ObtenerDataAvanceCarrera`
   con `{cPerCodigo: "", nPerAluRegCodigo}` y
   `cTablas: "Malla_Curricular,Malla_Curricular_grafPromedioNotaByCiclo,Malla_Curricular_grafAvanceCarrera,Malla_Curricular_grafTipoCurso,DatosPersonales,Competencias,PuestoAcademico"`.

Devuelve, entre otras tablas:

| Tabla | Contenido |
|-------|-----------|
| `Malla_Curricular` | una fila por curso del plan: `Nota` (0–20, entero), `nPromedioAcumulado`, `perMerito`, `TotalCreditos`, `TotalCursos`, `Periodo`, `nCiclo`, `Estado` |
| `grafPromedioNotaByCiclo` | `{Periodo, promedioPorCiclo}`: el gráfico de promedios por ciclo |
| `grafAvanceCarrera` | `totalCreditos`, `totalCreditosAprobados` |
| `DatosPersonales`, `DOMICILIO`, `EMAIL`, `Telefonos`, … | ficha del alumno |

- El "PROMEDIO ACUMULADO" del tablero es `Malla_Curricular[0].nPromedioAcumulado`
  (el mismo valor en todas las filas).
- Equivale al promedio ponderado por créditos de los cursos con `Nota > 0` de la
  malla **vigente**. Verificado: `Σ(Nota×créditos)/Σcréditos` coincide a dos
  decimales con `nPromedioAcumulado`.
- No calcularlo con `HISTORIAL_CURSOS`: mezcla la currícula vigente con las no
  vigentes y da otro número.
- `perMerito` es el orden de mérito del alumno.

## 9. Secciones del menú

Rutas de las secciones que el campus muestra en la barra superior. Sirven para
saber dónde vive cada función antes de agregar un comando.

| Menú | Ruta |
|------|------|
| Mi tablero | `POST /Campus/ua/Tablero/Perfil/Camp_Virt_Perfil.aspx` |
| Mis cursos · actuales | `Alu_CursosActuales.aspx` (`Alu_ObtenerCursosActuales`) |
| Mis cursos · historial | ver §7 |
| Mis cursos · autoformativos | `POST /Campus/ua/ServiciosUniversitarios/CursosAutoformativos/Camp_Virt_CursosAutoformativos.aspx` |
| Sesiones en línea · grabaciones | Mongo `getInfoMongoCurso` con `caso: "alumno/sesionZoomGrabaciones/<cPerCodigo>/<nGruCodigo>/<nSesion>/<nPerfil>"` |
| Horario de clases | `Alu_HorarioClase.aspx/Alu_ObtenerHorarioClase` |
| Mis finanzas · pendientes | `MisFinanzas/Camp_Virt_PagosPendientes.aspx/Alu_ObtenerPagosPendientes` |
| Mis finanzas · historial | `POST /Campus/ua/MisFinanzas/Camp_Virt_HistorialPagos.aspx` |
| Mis finanzas · comprobantes | `POST /Campus/ua/MisFinanzas/Camp_Virt_ComprobantesPagos.aspx` |
| Mis finanzas · convenio | `POST /Campus/ua/ServiciosEnLinea/BeneficioConvenio/Camp_Virt_BeneficioConvenio.aspx` |
| Servicios universitarios · defensoría | `POST /Campus/ua/ServiciosEnLinea/DefensoriaUniversitaria/Camp_Virt_DefensoriaUniversitaria.aspx` |
| Servicios en línea · talleres | `POST /Campus/ua/ServiciosEnLinea/Talleres/Camp_Virt_Talleres.aspx` |
| Servicios en línea · rezagado | `POST /Campus/ua/ServiciosEnLinea/ExamenRezagado/Camp_Virt_ExamenRezagado.aspx` |
| Servicios en línea · carné | `ServiciosAcademicos/CarneUniversitario/Camp_Virt_RequisitosCarneUniversitario.aspx` |
| Servicios en línea · trámites | `queryBBDD` (§ del plan de datos académicos) |

Las demás secciones (biblioteca, portal de empleabilidad, cartas de
presentación, laboratorios, tutorías) están en el menú pero todavía no se
mapearon sus endpoints.

## 10. Subida de archivos (`entregar`)

Los dos flujos suben primero el archivo a `/Uploads` y después lo registran con
un WebMethod distinto. El contrato vive en `uploadform.py`; la corrida (una
subida y un registro), en `uploader.py`.

### 10.1 Subida común

```
POST /GlobalAplication/FileUpload.ashx
Content-Type: multipart/form-data; boundary=…

folder0=            # vacío
file0=<bytes>       # el archivo
param0=<nombre>     # solo tareas, opcional: cambia el nombre base
path0=/Uploads
```

- Respuesta: el nombre con el que quedó guardado, como **texto**
  (`209901_ENTREGA.zip`); algunas versiones contestan `{"d": ...}`.
- Un archivo por entrega. Límite propio: 25 MB. El widget de carpeta anuncia
  5 MB, pero es solo cliente: el servidor aceptó más de 5 MB en una pasada.
- `param0` se usa como nombre base; omitirlo conserva el nombre original.

### 10.2 Carpeta compartida

1. XML `<Recursos>`: `url`, `nDocLinTipo=2`, `titulo`, `descripcion`,
   `Accion=A1`, `nForoSesion`, `cForoPadre=0`, `nEstado=1`, `cDocCodigo`,
   `nSubTipoMaterial=65003210`, `nCarCodigo=2`, `nDocLinGrupo=<carpeta>`,
   `nPerRelacion=1`, `encualquiermomento=0`.
2. `POST /CampusVirtual/ua/Docente/MisCursos/Doc_CursosActuales.aspx/Doc_InsertarRecurso`
   con `{xml}`.
3. Éxito: `InsertarRecursos[0].nUAEstado == 1`; el `nDocLinNum` nuevo sale del
   mismo registro. `nUAEstado != 1` es rechazo **aunque el archivo ya esté en
   `/Uploads`**: no hay fallback automático a tarea.
4. Sincronización Mongo opcional (best-effort): `setCarpetaRecurso` en
   `Alu_CursosActuales.aspx/setCarpetaRecurso` con
   `{nDocLinNum: <carpeta>, nGruCodigo, carpetaInformation, silaboId: "",
   sesionId: ""}`. `carpetaInformation` lleva `cDocLinUrl`, `Archivo`,
   `cPerCodigo`, `cDocLinComentario`, `cDocLinDescripcion`, `nDocLinNum`,
   `nDocLinGrupo`, `autor` y `fechaRegistro`. `cPerCodigo` es el código de
   alumno y solo se lee al sincronizar; si falla, la entrega ya quedó
   registrada y solo se avisa.

`nForoSesion` es la semana donde vive la carpeta. La carpeta trae su `nSesion`
en los recursos, así que la CLI mira primero la sesión activa (una lectura,
`getInformationDetailCurso` con `nSesion=0`) y solo si no está ahí recorre las
sesiones de a una, cortando en la primera coincidencia. `--sesion N` salta la
búsqueda; si la carpeta no aparece, se detiene en vez de mandar una semana
inventada. Coste de `--carpeta` sin `--sesion`: 1 lectura de la sesión activa
más 1 por sesión recorrida hasta encontrarla (el catálogo de cursos aparte, con
caché de 6 h).

### 10.3 Tarea

1. Multipart como en 10.1, **sin `param0`** salvo que se pida explícitamente.
2. XML `<TAREA>`: `url`, `titulo`, `descripcion`, `cDocCodigo`,
   `nDocLinNum=<tarea>`, `nGruCurso=<grupo>`, `Accion=A1`, `nRespTarea=0`,
   `IDDirectory` y `cUuid` (vacíos).
3. `POST /CampusVirtual/ua/Alumno/MisCursos/Alu_CursosActuales.aspx/Alu_InsertarTarea`
   con `{xml}`. Éxito: respuesta **numérica > 1** (es el `nRespTarea`); `1` es
   rechazo.
4. El `cDocCodigo` del XML sale del campo `cDocCodigo` del curso, que puede ser
   distinto de `codigo`/`cCurDetCod`; en tareas está confirmado contra el
   campus, en carpetas queda pendiente de confirmar.
5. Las tareas con antiplagio o rúbrica se registran igual, pero la CLI no
   replica Turnitin ni adjunta la rúbrica: eso queda del lado del campus.

### 10.4 Límites y pendientes

- No se implementa borrado (`Accion=A2`) ni edición: un archivo por corrida.
- `titulo` y `descripcion` se escapan con `xml.sax.saxutils.escape`.
- Una corrida = una autenticación, una subida y un registro (más el aviso Mongo
  opcional). Si el campus rechaza, se informa y se sale con código 4. Los
  registros no se reintentan ante 5xx o red caída (no son idempotentes); solo
  se repiten si la sesión venció (401), que no llegó a ejecutar el método.
- `--carpeta` gasta 1 lectura de la sesión activa y, si la carpeta no está ahí,
  1 por sesión recorrida; `--sesion N` evita ese recorrido.
- Pendiente de confirmar contra el campus: qué fechas o cupos evalúa
  `subirDocumento` cuando una carpeta responde `nUAEstado=0`, si las carpetas
  usan el mismo `cDocCodigo` que las tareas, y si `setCarpetaRecurso` necesita
  `silaboId`/`sesionId` con valor en alguna versión del campus.

