"""Sesion autenticada del campus: login, cookies y codigo de alumno.

El transporte (opener, jar y pausa entre pedidos) lo inyecta quien construye
el cliente; este modulo solo guarda el estado de la autenticacion.
"""

from __future__ import annotations

from http.cookiejar import CookieJar
from typing import Mapping, Protocol
from urllib.parse import urlencode, urljoin
from urllib.request import Request

from ..errors import AuthenticationError, SessionExpiredError
from .cookies import CookieStore
from .form import (
    LoginOutcome,
    LoginPageParser,
    build_login_data,
    classify_login,
    student_code_from_html,
)


class Transport(Protocol):
    """Lo que ``AuthSession`` necesita del transporte HTTP."""

    home_url: str
    jar: CookieJar
    cookies_path: str

    def send(self, request: Request): ...


class AuthSession:
    """Estado de la sesion: credenciales, cookie y codigo de alumno."""

    def __init__(
        self,
        transport: Transport,
        login_url: str,
        headers: Mapping[str, str],
    ) -> None:
        self._transport = transport
        self.login_url = login_url
        self.headers = headers
        self._cookies = CookieStore(transport.jar, transport.cookies_path)
        self._credentials: tuple[str, str] | None = None
        self._authenticated = False
        self._student_code = ""

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    @property
    def student_code(self) -> str:
        return self._student_code

    def authenticate(
        self, username: str, password: str, *, force_login: bool = False
    ) -> bool:
        """Reutiliza la cookie guardada o inicia sesion.

        Devuelve True si hubo un login nuevo (util para informar al usuario).
        """

        self._credentials = (username, password)
        if not force_login and self._cookies.load():
            self._authenticated = True
            return False
        self.login(username, password)
        return True

    def login(self, username: str, password: str) -> None:
        username = (username or "").strip()
        if not username or not password:
            raise AuthenticationError("Usuario y contrasena son obligatorios.")
        self._credentials = (username, password)

        with self._transport.send(Request(self.login_url, headers=self.headers)) as response:
            html = response.read().decode("utf-8", "replace")

        form = LoginPageParser()
        form.feed(html)
        action = urljoin(self.login_url, form.action or self.login_url)
        data = build_login_data(form, username, password)

        request = Request(
            action,
            data=urlencode(data).encode("utf-8"),
            headers={
                **self.headers,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": self.login_url,
            },
            method="POST",
        )
        with self._transport.send(request) as response:
            final_url = response.geturl()
            body = response.read().decode("utf-8", "replace")

        outcome = classify_login(final_url, body)
        if outcome.kind == LoginOutcome.REJECTED:
            raise AuthenticationError(
                "El campus rechazo las credenciales."
                + (f" Mensaje del campus: {outcome.detail}" if outcome.detail else "")
            )
        if outcome.kind == LoginOutcome.PASSWORD_CHANGE:
            raise AuthenticationError(
                "El campus acepto el usuario y la contrasena, pero exige cambiarla "
                "antes de dar acceso al panel. Entra al campus, actualizala y "
                "repite: autonoma login"
            )
        if outcome.kind == LoginOutcome.UNEXPECTED:
            raise AuthenticationError(
                "El login no llego al panel del campus (posible CAPTCHA o MFA)."
            )

        self._transport.home_url = final_url
        self._student_code = student_code_from_html(body)
        self._authenticated = True
        self._cookies.save()

    def relogin(self) -> None:
        if not self._credentials:
            raise SessionExpiredError(
                "La sesion del campus expiro y no hay credenciales para renovarla. "
                "Ejecuta: autonoma login"
            )
        username, password = self._credentials
        self.login(username, password)

    def logout(self) -> bool:
        """Borra la cookie guardada en disco y vacia el jar en memoria."""

        self._authenticated = False
        self._student_code = ""
        return self._cookies.clear()

    def cookie_header(self) -> str:
        """Cabecera Cookie para descargas fuera de esta sesion (hilos)."""

        return self._cookies.header()

    def cookie_names(self) -> list[str]:
        """Nombres de las cookies del jar, sin sus valores."""

        return self._cookies.names()

    def ensure_student_code(self) -> str:
        """Lee el codigo de alumno si aun no lo tenemos.

        Con la cookie guardada no hay login y el codigo solo aparece en
        Default.aspx; sin el, el historial responde vacio.
        """

        if self._student_code:
            return self._student_code
        home = self._transport.home_url
        request = Request(home, headers={**self.headers, "Referer": home})
        with self._transport.send(request) as response:
            html = response.read().decode("utf-8", "replace")
        self._student_code = student_code_from_html(html)
        return self._student_code

    def expire(self) -> None:
        """Marca la sesion como vencida; el proximo pedido renueva la cookie."""

        self._authenticated = False
