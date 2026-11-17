"""Sesion falsa para los tests de red: respuestas guionadas y jar real."""

from __future__ import annotations

import atexit
import tempfile
from http.cookiejar import Cookie, LWPCookieJar
from pathlib import Path
from typing import Any

COOKIE_NAME = "ASP.NET_SessionId"
COOKIE_VALUE = "de-ejemplo"


def _cookie(name: str = COOKIE_NAME, value: str = COOKIE_VALUE) -> Cookie:
    return Cookie(
        version=0, name=name, value=value, port=None,
        port_specified=False, domain="campus-de-ejemplo.edu", domain_specified=True,
        domain_initial_dot=False, path="/", path_specified=True, secure=False,
        expires=None, discard=False, comment=None, comment_url=None, rest={},
    )


def save_cookie(session: FakeSession) -> None:
    """Deja una cookie vigente guardada, como la de una corrida anterior."""

    session.jar.set_cookie(_cookie())
    Path(session.cookies_path).parent.mkdir(parents=True, exist_ok=True)
    session.jar.save(ignore_discard=True, ignore_expires=True)


class FakeSession:
    """Cumple el puerto de ``CampusSession`` sin tocar la red.

    Devuelve las respuestas en orden y repite la ultima cuando se acaba la
    lista, para los tests que esperan varios pedidos iguales. Un elemento
    ``BaseException`` de la lista se levanta en vez de devolverse.
    """

    def __init__(
        self,
        *responses: Any,
        timeout: float = 30.0,
        delay: float = 0.0,
        home_url: str = "",
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self.home_url = home_url
        self.host = ""
        self.pin_ip = ""
        self._tmp = tempfile.TemporaryDirectory()
        # El jar vive en un archivo; el directorio se cierra al salir aunque el
        # recolector no llegue a recoger esta sesion.
        atexit.register(self._tmp.cleanup)
        self.cookies_path = str(Path(self._tmp.name) / "session.cookies")
        self.jar = LWPCookieJar(self.cookies_path)
        self.responses = list(responses)
        self.requests: list[Any] = []
        self.attempts = 0
        self.closed = False

    def send(self, request: Any) -> Any:
        self.attempts += 1
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        self.closed = True
