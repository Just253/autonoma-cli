# Configuración, credenciales y caché

Todo lo que la CLI guarda en disco vive en **un solo directorio de
configuración**:

- Windows: `%APPDATA%\autonoma-cli`
- Linux/macOS: `~/.config/autonoma-cli`

| Archivo | Qué guarda |
|---------|------------|
| `credentials.json` | Usuario y contraseña (DPAPI en Windows, `0600` en el resto). |
| `credentials.txt` | Alternativa editable a mano, en texto plano. |
| `session.cookies` | Cookie `ASP.NET_SessionId`. |
| `settings.json` | Preferencias opcionales (ver abajo). |
| `cache/cache.json` | Cursos, horario e historial, 6 horas. |

Nada de esto va al repositorio: `.gitignore` excluye credenciales, cookies,
preferencias, caché y `descargas/`.

## Credenciales

Precedencia al leer:

1. `AUTONOMA_USER` y `AUTONOMA_PASSWORD` (las dos juntas).
2. `credentials.txt`, si tiene usuario y contraseña completos.
3. `credentials.json`.

- En Windows la contraseña de `credentials.json` se cifra con **DPAPI**
  (`CryptProtectData`): solo tu usuario de Windows puede descifrarla.
- En Linux/macOS se guarda con permisos `0600` y se avisa en el primer guardado.
- `autonoma logout --credenciales` borra cookie y credenciales.

Evitá `--password` en la terminal: queda en el historial. Si se omite, la CLI la
pide sin mostrarla.

### `credentials.txt`

```ini
# Credenciales del Campus Virtual - autonoma-cli
usuario=
password=
```

- Alias de usuario: `usuario`, `user`, `username`, `correo`.
- Alias de contraseña: `password`, `pass`, `clave`, `contrasena`, `contraseña`.
- Separador `=` o `:`; comillas alrededor del valor se ignoran.
- Comentarios con `#` o `;`.
- Si está vacío o incompleto, se usan las credenciales cifradas.

Comandos: `autonoma credenciales` (crear/mostrar), `--abrir` (editor del
sistema), `--borrar` (volver al cifrado).

## Variables de entorno

| Variable | Efecto |
|----------|--------|
| `AUTONOMA_USER` / `AUTONOMA_PASSWORD` | Credenciales sin tocar disco. |
| `AUTONOMA_BASE_URL` | Otro dominio del campus. |
| `AUTONOMA_CLI_HOME` | Otra carpeta de configuración (tests). |
| `AUTONOMA_OUT` | Carpeta de descargas por defecto. |
| `AUTONOMA_DELAY` | Pausa entre peticiones (segundos). |
| `AUTONOMA_TIMEOUT` | Timeout por petición (segundos). |
| `AUTONOMA_WORKERS` | Descargas en paralelo por defecto (4). |
| `NO_COLOR` | Desactiva color. |

## `settings.json`

Opcional y editable a mano; la CLI lo lee al arrancar pero nunca lo escribe.
Claves: `base_url`, `timeout`, `delay`, `workers`, `out_dir`, `max_sessions`.

Precedencia: opciones de la línea de comandos > variables de entorno >
`settings.json` > valores por defecto (30 s, 0.5 s, 4 descargas en paralelo,
`./descargas`).

## Caché

- `cache/cache.json` guarda cursos, horario por grupo e historial, con 6 horas
  de vigencia.
- Es un solo documento con `version` y `base_url`: si cambia el campus, la caché
  se descarta sola en vez de mezclar datos.
- `autonoma cache` muestra el estado; `autonoma cache --borrar` la vacía.
- `--refresh` ignora la caché en esa corrida.
- Al guardar, la CLI borra los `cursos.json` y `horario.json` de versiones
  anteriores.

## Descargas

Destino, en orden: `--out` > `AUTONOMA_OUT` > `out_dir` de `settings.json` >
`./descargas`. Ver la estructura en [GUIA.md](GUIA.md#6-descargar).
