"""Politica de llamadas a los WebMethods del campus.

Aca viven los reintentos, el relogin y la subida; los endpoints y sus payloads
estan en ``methods.py``. El contexto es de solo lectura: el estado mutable
(cookies, sesion vencida) sigue en ``auth`` y en el transporte.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urljoin
from urllib.request import Request

from ..auth import LOGIN_REDIRECT, AuthSession, Transport
from ..errors import (
    AuthenticationError,
    CampusError,
    CampusHTTPError,
    ProtocolError,
    SessionExpiredError,
)
from .json import unwrap

DEFAULT_PAGE = "/Campus/Default.aspx"
EXPIRED = "La sesion del campus expiro."


@dataclass(frozen=True)
class ApiContext:
    """Lo que una llamada necesita del cliente, sin estado propio."""

    base_url: str
    headers: Mapping[str, str]
    session: Transport
    auth: AuthSession
    retries: int


def call_once(
    ctx: ApiContext, method: str, payload: Mapping[str, Any], page: str
) -> Any:
    """Hace un pedido al WebMethod y desenvuelve la respuesta."""

    page_url = urljoin(ctx.base_url + "/", page.lstrip("/"))
    endpoint = f"{page_url.rstrip('/')}/{method}"
    request = Request(
        endpoint,
        data=json.dumps(dict(payload), ensure_ascii=False).encode("utf-8"),
        headers={
            **ctx.headers,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": ctx.session.home_url,
        },
        method="POST",
    )
    with ctx.session.send(request) as response:
        final_url = response.geturl()
        raw = response.read().decode("utf-8", "replace")

    if LOGIN_REDIRECT.search(final_url):
        raise SessionExpiredError(EXPIRED)
    if not raw.strip():
        return None
    try:
        payload_json = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:160].replace("\n", " ")
        raise ProtocolError(f"{method} no devolvio JSON: {snippet!r}") from exc
    return unwrap(payload_json)


def call(
    ctx: ApiContext,
    method: str,
    payload: Mapping[str, Any] | None = None,
    *,
    page: str = DEFAULT_PAGE,
    allow_relogin: bool = True,
    retry_transient: bool = True,
) -> Any:
    """Llama a un WebMethod y desenvuelve la respuesta.

    ``retry_transient=False`` deja un solo intento ante 5xx o red caida:
    los registros de entrega (``Doc_InsertarRecurso``, ``Alu_InsertarTarea``)
    no son idempotentes y repetirlos puede duplicar el envio. Solo se
    reintenta por autenticacion (401 o sesion vencida), que no llego a
    ejecutar el metodo.
    """

    payload = payload or {}
    last_error: Exception | None = None
    for attempt in range(1, ctx.retries + 1):
        try:
            if not ctx.auth.authenticated:
                ctx.auth.relogin()
            return call_once(ctx, method, payload, page)
        except SessionExpiredError:
            ctx.auth.expire()
            if allow_relogin:
                ctx.auth.relogin()
                return call_once(ctx, method, payload, page)
            raise
        except CampusHTTPError as exc:
            if exc.status_code == 401:
                # La cookie vencio sin redirigir al login: el campus responde 401.
                ctx.auth.expire()
                if allow_relogin:
                    ctx.auth.relogin()
                    return call_once(ctx, method, payload, page)
                raise SessionExpiredError(EXPIRED) from exc
            if (
                retry_transient
                and exc.status_code in {500, 502, 503, 504}
                and attempt < ctx.retries
            ):
                last_error = exc
                time.sleep(1.5 * attempt)
                continue
            raise
        except CampusError as exc:
            if isinstance(exc, (AuthenticationError, ProtocolError)) or not retry_transient:
                raise
            if attempt < ctx.retries:
                last_error = exc
                time.sleep(1.5 * attempt)
                continue
            raise
    raise last_error or CampusError(f"{method} fallo sin detalle.")


def post_raw(
    ctx: ApiContext,
    body: bytes,
    *,
    content_type: str,
    page: str,
) -> str:
    """Manda un cuerpo ya armado y devuelve el texto de la respuesta.

    Es un solo envio: solo se repite si la sesion habia vencido y el campus no
    llego a guardar nada (redireccion al login o HTTP 401).
    """

    request = Request(
        urljoin(ctx.base_url + "/", page.lstrip("/")),
        data=body,
        headers={
            **ctx.headers,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": content_type,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": ctx.session.home_url,
        },
        method="POST",
    )
    try:
        return _send_text(ctx, request)
    except SessionExpiredError:
        pass
    except CampusHTTPError as exc:
        if exc.status_code != 401:
            raise
    ctx.auth.expire()
    ctx.auth.relogin()
    return _send_text(ctx, request)


def _send_text(ctx: ApiContext, request: Request) -> str:
    with ctx.session.send(request) as response:
        final_url = response.geturl()
        raw = response.read().decode("utf-8", "replace")
    if LOGIN_REDIRECT.search(final_url):
        raise SessionExpiredError(EXPIRED)
    return raw
