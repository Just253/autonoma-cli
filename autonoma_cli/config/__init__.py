"""Configuracion local: credenciales, cookies de sesion y preferencias.

Las credenciales se guardan fuera del repositorio, en el directorio de
configuracion del usuario:

  Windows  %APPDATA%\\autonoma-cli
  Linux    ~/.config/autonoma-cli
  macOS    ~/.config/autonoma-cli

En Windows el secreto se cifra con DPAPI (CryptProtectData): solo la misma
cuenta de Windows puede descifrarlo. En otras plataformas se guarda en claro
con permisos 0600 y se avisa al usuario.

Se puede cambiar la carpeta con AUTONOMA_CLI_HOME (util para pruebas).

El paquete parte el archivo unico por tema: ``paths`` (rutas y constantes),
``io`` (escritura privada), ``crypto`` (DPAPI), ``credentials``, ``plain``
(``credentials.txt``) y ``settings``. Este ``__init__`` reexporta la misma
superficie publica que tenia ``config.py``.
"""

from __future__ import annotations

from .paths import (
    APP_NAME,
    CACHE_DIRNAME,
    COOKIES_FILE,
    CREDENTIALS_FILE,
    DEFAULT_BASE_URL,
    PINNED_FILE,
    PLAIN_CREDENTIALS_FILE,
    SETTINGS_FILE,
    cache_dir,
    cookies_path,
    credentials_path,
    ensure_home,
    home,
    pinned_path,
    plain_credentials_path,
    settings_path,
)
from .io import write_private_text
from .plain import (
    PLAIN_CREDENTIALS_TEMPLATE,
    clear_plain_credentials,
    create_plain_credentials_file,
    read_plain_credentials,
)
from .credentials import (
    METHOD_LABELS,
    Credentials,
    clear_credentials,
    credentials_info,
    load_credentials,
    save_credentials,
)
from .settings import Settings, load_settings, save_settings

__all__ = [
    # constantes y rutas
    "APP_NAME",
    "DEFAULT_BASE_URL",
    "CREDENTIALS_FILE",
    "PLAIN_CREDENTIALS_FILE",
    "COOKIES_FILE",
    "PINNED_FILE",
    "SETTINGS_FILE",
    "CACHE_DIRNAME",
    "home",
    "ensure_home",
    "credentials_path",
    "plain_credentials_path",
    "cookies_path",
    "pinned_path",
    "settings_path",
    "cache_dir",
    # credenciales
    "METHOD_LABELS",
    "Credentials",
    "save_credentials",
    "load_credentials",
    "clear_credentials",
    "credentials_info",
    # credenciales en texto plano
    "PLAIN_CREDENTIALS_TEMPLATE",
    "create_plain_credentials_file",
    "read_plain_credentials",
    "clear_plain_credentials",
    # escritura privada (la cache la usa via ``config.write_private_text``)
    "write_private_text",
    # preferencias
    "Settings",
    "load_settings",
    "save_settings",
]

# Helpers internos con nombre publico en su modulo, reexportados para que
# ``config._foo`` siga funcionando. No van en ``__all__`` porque no son parte
# de la superficie estable del paquete.
from .crypto import blob, protect, unprotect  # noqa: E402, F401
from .io import write_private  # noqa: E402, F401
from .plain import parse_plain_credentials  # noqa: E402, F401
