"""Diagnostico de red y conexiones TLS contra el campus.

El campus vive detras de un balanceador que rota IPs en minutos: una
resolucion cacheada puede terminar en un servidor con el certificado de otro
sitio. Aca se resuelve el host, se valida el certificado de cada IP, se
recuerda la ultima IP buena y se ofrece la conexion HTTPS fijada a esa IP.

Solo stdlib: lo importan el cliente y las descargas, y el archivo del pin lo
ubica quien llama, porque este modulo no conoce la configuracion.
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.request import HTTPSHandler, Request

# Cuanto se reusa la ultima IP que valido certificado. El balanceador del
# campus rota en minutos: mas que esto y la IP recordada puede ser de otro
# cliente del mismo proveedor.
PINNED_TTL = 600.0


def cert_mismatch(exc: BaseException) -> bool:
    """True si el certificado verifica pero es de otro sitio.

    Pasa con el balanceador del campus: AWS retira una IP del ALB y la
    reasigna a otro cliente, asi que una resolucion cacheada puede terminar
    en un servidor con un certificado ajeno (``Hostname mismatch``).
    """

    reason = getattr(exc, "reason", exc)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    text = str(reason)
    return "CERTIFICATE_VERIFY_FAILED" in text and "not valid for" in text


def flush_dns() -> None:
    """Vacia la cache DNS del sistema sin pedir privilegios (best-effort)."""

    try:
        import ctypes

        ctypes.WinDLL("dnsapi").DnsFlushResolverCache()
    except Exception:  # noqa: BLE001 - fuera de Windows no existe dnsapi
        pass


def resolved_ips(host: str, port: int) -> list[str]:
    """IPs que el sistema devuelve para el campus, sin repetir."""

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    return list(dict.fromkeys(info[4][0] for info in infos))


def valid_ip(host: str, port: int, timeout: float) -> str:
    """Primera IP que hoy presenta un certificado valido para ``host``."""

    context = ssl.create_default_context()
    for ip in resolved_ips(host, port):
        try:
            with socket.create_connection((ip, port), timeout=timeout) as raw:
                with context.wrap_socket(raw, server_hostname=host):
                    return ip
        except OSError:
            continue
    return ""


def load_pin(path: Path, host: str) -> str:
    """IP validada hace menos de ``PINNED_TTL`` para ``host``, o cadena vacia."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(payload, dict) or payload.get("host") != host:
        return ""
    try:
        age = time.time() - float(payload.get("checked_at", 0))
    except (TypeError, ValueError):
        return ""
    if not 0 <= age <= PINNED_TTL:
        return ""
    return str(payload.get("ip") or "")


def save_pin(path: Path, host: str, ip: str) -> None:
    """Recuerda la IP buena para que la proxima corrida no repita el salto."""

    if not ip:
        return
    payload = json.dumps({"host": host, "ip": ip, "checked_at": time.time()})
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    except OSError:
        pass


def drop_pin(path: Path) -> None:
    """Olvida la IP recordada; si no habia archivo, no hace nada."""

    try:
        path.unlink()
    except OSError:
        pass


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS contra una IP fija, conservando el Host y el SNI del campus."""

    _pin_ip = ""

    def connect(self) -> None:
        if not self._pin_ip or self._tunnel_host:
            return super().connect()
        original = self._create_connection
        self._create_connection = lambda address, timeout=None, source_address=None: (
            socket.create_connection((self._pin_ip, address[1]), timeout, source_address)
        )
        try:
            super().connect()
        finally:
            self._create_connection = original


class PinnedHTTPSHandler(HTTPSHandler):
    """Handler que fija la IP de destino cuando hay que saltar una IP muerta."""

    pin_ip = ""

    def https_open(self, req: Request) -> Any:
        pin = self.pin_ip

        class Connection(PinnedHTTPSConnection):
            _pin_ip = pin

        return self.do_open(Connection, req)
