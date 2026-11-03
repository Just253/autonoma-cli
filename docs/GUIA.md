# Guía de uso

Recorridos por tarea. La lista completa de flags está en [CLI.md](CLI.md); acá
solo aparece lo que hace falta para cada flujo.

## 1. Comprobar la sesión

```powershell
autonoma whoami
```

Muestra usuario, código de alumno, campus y de qué archivo salieron las
credenciales. Si la cookie venció, la CLI vuelve a iniciar sesión sola.

## 2. Elegir un curso

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

El `nGruCodigo` es la llave estable: no cambia entre periodos y sirve para
nombrar un curso en cualquier comando. El índice, en cambio, depende de la
tabla que estés mirando.

## 3. Ver el sílabo

```powershell
autonoma curso 1
autonoma curso 90000001 --json
```

Lista las sesiones con fechas, tema, logro y la marca de sesión activa.

## 4. Horario y aulas

```powershell
autonoma horario --hoy
autonoma horario
autonoma horario --dia 15/03/2099
autonoma horario --desde 01/04/2099 --hasta 15/04/2099
autonoma horario ejemplo --todo
```

```
Hoy, 15/03/2099 · 1 sesion

Martes 15/03/2099
Hora         Curso                       Aula                            Tipo        Ses.
-----------  --------------------------  ------------------------------  ----------  ----
19:30-22:30  CURSO DE EJEMPLO UNO        A-101 (Laboratorio de Ejemplo)  Presencial  08

  08 · Tema de ejemplo de la sesion.
```

- `Aula` es el campo `ambiente`: el aula física o `Sala zoom`.
- `Tipo` distingue `Presencial`, `Sincrona` y `Asincrona`.
- Sin opciones, los próximos 7 días. Solo entran los cursos activos; para uno
  terminado hay que nombrarlo o pasar `--activos`.

Los ejemplos de salida de esta guía son ilustrativos: los datos reales son los
que devuelva el campus.

## 5. Ver recursos antes de descargar

```powershell
autonoma recursos 1
autonoma recursos 1 --sesion 4
autonoma recursos 90000001 --json
```

Cada recurso trae tipo (archivo, tarea, evaluación, foro, SCORM), fecha y
extensión. Solo los que tienen `url` se pueden descargar.

## 6. Descargar

Primero simular; sobre todo si es un curso completo:

```powershell
autonoma descargar 1 --seco
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

Filtros útiles:

```powershell
autonoma descargar 1 --solo "presentacion"
autonoma descargar 1 --tipo tarea
autonoma descargar 1 --seco
```

Y para todos los cursos, con cuidado:

```powershell
autonoma todo --seco
autonoma todo --out "$HOME\Descargas\autonoma"
```

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
- `manifest.json` guarda tamaño y sha256. Si el archivo existe con el mismo
  tamaño, se omite y se marca `[igual]`.

## 7. Ver notas y promedio

```powershell
autonoma notas
autonoma notas 1
autonoma notas 90000001 --json
```

```
Curso                    Periodo  Ciclo  Acumulado  Avance
-----------------------  -------  -----  ---------  ------
CURSO DE EJEMPLO UNO     209901       1       9.60     50%
CURSO DE EJEMPLO DOS     209901       1          0      0%
```

`Acumulado` es la suma de `nota × peso` de los criterios ya calificados, sobre
20. **No es un promedio**: mientras falten criterios con peso alto, el máximo
alcanzable tampoco es 20. `Avance` es el porcentaje del curso ya evaluado, no
la nota.

El detalle por criterio, con fechas y sesión:

```powershell
autonoma notas 1
```

```
CURSO DE EJEMPLO UNO
  periodo 209901 · ciclo 1 · grupo 1A1-A · 4 creditos

Criterio  Peso   Nota  Sesion  Desde       Hasta
--------  ----  -----  ------  ----------  ----------
EC          10  20.00       4  01/03/2099  03/03/2099
EP          40  19.00       8  01/05/2099  03/05/2099
EF          50      -      16  01/06/2099  03/06/2099

Acumulado 9.6 / 20 (solo 50 % evaluado)
Actualizado 15/03/2099 19:30:00
```

Los periodos cerrados no tienen criterios: su nota final es `nPromocional` y
sale con `--todos`, en una segunda tabla sin repetir el periodo en curso:

```powershell
autonoma notas --todos
```

```
Periodos cerrados

Periodo  Ciclo  Curso                    Cred.  Nota
-------  -----  -----------------------  -----  ----
209801       1  CURSO DE EJEMPLO DOS         4    15
```

Nombrar un curso cerrado también sirve: la CLI lo busca en el historial y
muestra la nota final en vez de criterios.

```powershell
autonoma notas 90000011
```

```
CURSO DE EJEMPLO DOS
  periodo 209801 · ciclo 1

Nota final: 15
Periodo cerrado: el campus no publica criterios para cursos cerrados.
```

El promedio oficial es el del tablero, no el del historial:

```powershell
autonoma notas --promedio
autonoma notas 1 --promedio
```

```
Promedio oficial

Dato                    Valor
----------------------  ----------------------
Acumulado del tablero   14.35
Calculado por creditos  14.35 (90 creditos)
Creditos                90 de 120 aprobados
Merito                  12
Promedio 209901         13.50
```

- `--promedio` sale del tablero (`ObtenerDataAvanceCarrera`). No lo calcules con
  `--todos`: el historial mezcla la currícula vigente con las anteriores y da
  otro número.
- Se puede combinar con `CURSO` y con `--todos`.
- `--todos` es para la lista: con `CURSO` no cambia la salida, porque un curso
  cerrado ya muestra su nota final.
- Las notas **no se cachean**: los criterios y el promedio oficial se piden al
  campus en cada corrida. El catálogo con el que se arma la lista sí sale de la
  caché de cursos e historial, así que `--refresh` sirve para refrescar ese
  catálogo (y los cerrados de `--todos`).

## 8. Periodos anteriores

```powershell
autonoma historial
autonoma historial --periodo 209801
autonoma historial --ciclo 3 --json
```

Recorre **todas las currículas** del alumno, así que aparecen los periodos
cerrados aunque el curso haya quedado en un plan antiguo. `Estado` es lo que
reporta el campus (`APROBADA`, `EN PROCESO`, …).

Los cursos del historial funcionan con los mismos comandos:

```powershell
autonoma curso 90000011
autonoma recursos 90000011
autonoma descargar 90000011 --seco
```

## 9. Filtrar cursos

```powershell
autonoma cursos --ciclo 8
autonoma cursos --periodo 209802
autonoma cursos --carrera "ejemplo"
autonoma cursos --activos
```

`--ciclo` y `--periodo` comparan por igualdad; `--carrera` busca dentro del
nombre sin acentos ni mayúsculas. Se combinan entre sí y con `--curso` en
`todo`. Valen en `cursos`, `horario`, `todo`, `historial` y `notas`. Filtran lo
que devuelve el campus: para periodos viejos, `historial`.

## Errores comunes

| Síntoma | Qué hacer |
|---------|-----------|
| `error: No hay credenciales guardadas` | `autonoma credenciales --abrir` y completar el archivo, o `autonoma login`. |
| `login: El campus rechazo las credenciales` | La clave cambió o el archivo tiene un typo. No la pidas en el chat. |
| `campus: No se pudo conectar` | Red o VPN. Los 5xx se reintentan solos. |
| `certificate verify failed: ... not valid for 'virtual.autonoma.edu.pe'` | El balanceador del campus rotó su IP y la caché DNS quedó vieja: la CLI ya reintenta por otra IP sola. Si insiste, `ipconfig /flushdns` (y en Portmaster, apagar el *stale cache* de DNS). |
| `campus: El campus respondio HTTP 401` | Sesión vencida; la CLI reloguea sola. Si insiste, `autonoma login`. |
| Todo vacío o 0 recursos | Curso sin materiales publicados o periodo cerrado; probá `--refresh`. |
| Un recurso no baja | Puede no tener archivo (carpeta, foro, tarea sin adjunto) o el campus cambió un endpoint. |
| `error: unrecognized arguments` | El flag no existe para ese comando: `autonoma <comando> --help`. |
| `Sin criterios de evaluacion todavia.` | El curso activo no tiene criterios publicados todavía. Si es de un periodo cerrado, nombrá el curso para ver su nota final o usá `--todos`. |
| Nota vacía (`-`) en un periodo cerrado | El campus no publicó `nPromocional` para ese curso: no hay nota final que mostrar. Revisá la boleta en el campus o reintentá más tarde. |
| `--todos` no trae un curso cerrado | Lo dejó fuera un filtro (`--periodo`, `--ciclo`, `--carrera`) o esa currícula no está en el historial: probá `autonoma historial --curso TEXTO`. |
| El acumulado no coincide con el promedio del tablero | Son números distintos: `Acumulado` es parcial y por curso; el oficial sale de `--promedio`. |
