"""Formulario de login del campus: campos, clasificacion y codigo de alumno.

Sin red ni disco: recibe el HTML que devolvio el campus y decide que paso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import ClassVar

from ..models import strip_html

LOGIN_REDIRECT = re.compile(r"/Campus/Login\.aspx(?:$|[?#])", re.I)
_FAILURE_TEXT = re.compile(r'id="FailureText"[^>]*>(.*?)</span>', re.I | re.S)
# El campus obliga a rotar la contrasena y manda a CambioContrasena.aspx antes
# de dejar entrar al panel; no es un fallo de credenciales ni CAPTCHA/MFA.
_PASSWORD_CHANGE = re.compile(r"/Campus/CambioContrasena\.aspx", re.I)


class LoginPageParser(HTMLParser):
    """Extrae el action del formulario y sus campos ocultos.

    El HTML del campus repite el atributo ``name`` en algunos inputs
    (``name="txtUsuario" ... name="email-username"``). Por eso se toma la
    PRIMERA aparicion de cada atributo y no un ``dict(attrs)``.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.action: str | None = None
        self.hidden: dict[str, str] = {}
        self.submit: dict[str, str] = {}
        self._form_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values: dict[str, str] = {}
        for key, value in attrs:
            if key and key not in values:
                values[key] = value or ""

        if tag == "form":
            if self.action is None or values.get("id") == "frmLogin" or values.get("name") == "frmLogin":
                self.action = values.get("action", "")
            self._form_depth += 1
            return

        name = values.get("name", "").strip()
        if tag != "input" or not name:
            return

        input_type = (values.get("type") or "text").lower()
        if input_type == "hidden":
            self.hidden[name] = values.get("value", "")
        elif input_type in {"submit", "button"}:
            self.submit[name] = values.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._form_depth:
            self._form_depth -= 1


def build_login_data(
    form: LoginPageParser, username: str, password: str
) -> dict[str, str]:
    """Campos del POST: ocultos del formulario, usuario, clave y boton."""

    data = dict(form.hidden)
    data["txtUsuario"] = username
    data["txtPassword"] = password
    if "btn_ingresar" in form.submit:
        data["btn_ingresar"] = form.submit["btn_ingresar"]
    elif form.submit:
        name, value = next(iter(form.submit.items()))
        data[name] = value
    else:
        data["btn_ingresar"] = "Ingresar"
    return data


def student_code_from_html(html: str) -> str:
    """Codigo de alumno que el panel deja en un input oculto."""

    patterns = (
        r'id="cPerCodigo"[^>]*value="([^"]+)"',
        r'id="txtcPerCodigoLog"[^>]*value="([^"]+)"',
        r'(?:cPerCodigo|CPERCODIGO)\s*[:=]\s*["\']([^"\']+)',
    )
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return match.group(1).strip()
    return ""


@dataclass(frozen=True)
class LoginOutcome:
    """Que contesto el campus al POST de login y, si lo dijo, su mensaje."""

    kind: str
    detail: str = ""

    OK: ClassVar[str] = "ok"
    REJECTED: ClassVar[str] = "rejected"
    PASSWORD_CHANGE: ClassVar[str] = "password_change"
    UNEXPECTED: ClassVar[str] = "unexpected"


def classify_login(final_url: str, body: str) -> LoginOutcome:
    """Clasifica la respuesta del POST sin lanzar excepciones."""

    if LOGIN_REDIRECT.search(final_url):
        match = _FAILURE_TEXT.search(body)
        detail = strip_html(match.group(1)) if match else ""
        return LoginOutcome(LoginOutcome.REJECTED, detail)
    if _PASSWORD_CHANGE.search(final_url):
        return LoginOutcome(LoginOutcome.PASSWORD_CHANGE)
    if "/Campus/Default.aspx" not in final_url and 'id="cPerCodigo"' not in body:
        return LoginOutcome(LoginOutcome.UNEXPECTED)
    return LoginOutcome(LoginOutcome.OK)
