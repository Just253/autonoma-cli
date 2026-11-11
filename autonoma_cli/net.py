"""Diagnostico de red compartido por el cliente y las descargas.

Vive aparte para que ``downloader.py`` no importe nombres privados de
``client.py``: el certificado del campus puede venir de una IP ajena y la
cache DNS del sistema puede apuntar a esa IP vieja.

S1 suma aca el pin de IP y las conexiones TLS; por ahora solo estas dos.
"""

from __future__ import annotations

import ssl


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
