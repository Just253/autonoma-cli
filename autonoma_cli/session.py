"""Sesion HTTP del campus: transporte, cookies y pin de IP.

El campus vive detras de un balanceador que rota IPs en minutos: una
resolucion cacheada puede terminar en un servidor con el certificado de otro
sitio. La sesion recuerda la ultima IP que valido el certificado, la reusa
mientras dure el TTL y rehace la conexion sin pin cuando la recordada deja de
responder.

El archivo de cookies y el del pin los ubica quien construye la sesion: este
modulo no conoce la configuracion del usuario.
"""

from __future__ import annotations

import ssl
import time
from http.cookiejar import LWPCookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from . import net
from .errors import CampusError, CampusHTTPError

_HOME_PAGE = "Campus/Default.aspx"


class CampusSession:
    """Conexion al campus: opener, cookies, pin de IP y pausa entre pedidos.

    El jar se crea una sola vez y es el mismo que recibe el
    ``HTTPCookieProcessor`` del opener, asi que las cookies que guarda el
    campus viajan en cada pedido que hace la sesion.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        delay: float = 0.5,
        cookies_path: str,
        pinned_path: Path,
    ) -> None:
        self.timeout = float(timeout)
        self.delay = max(0.0, float(delay))
        self.cookies_path = cookies_path
        self.jar = LWPCookieJar(cookies_path)
        parts = urlsplit(base_url)
        self.host = parts.hostname or ""
        self._port = parts.port or (443 if parts.scheme == "https" else 80)
        # El panel de inicio es el Referer de los WebMethods; el login lo
        # reemplaza por la URL final cuando el campus redirige a otra pagina.
        self.home_url = urljoin(base_url + "/", _HOME_PAGE)
        self._pinned_path = pinned_path
        self._pin_handler = net.PinnedHTTPSHandler()
        self._opener = build_opener(HTTPCookieProcessor(self.jar), self._pin_handler)
        self._last_request = 0.0
        self.pin_ip = net.load_pin(pinned_path, self.host)

    @property
    def pin_ip(self) -> str:
        """IP fijada en el handler; asignarla no la guarda en disco."""

        return self._pin_handler.pin_ip

    @pin_ip.setter
    def pin_ip(self, value: str) -> None:
        self._pin_handler.pin_ip = value

    def _wait(self) -> None:
        """Espera el ``delay`` configurado desde el pedido anterior."""

        remaining = self.delay - (time.monotonic() - self._last_request)
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()

    def _route_around(self) -> bool:
        """Salta una IP que ya no es del campus y fija una que si lo es.

        El ALB del campus publica TTL de 60 s: cuando rota, la IP anterior
        puede quedar en la cache DNS y responder con el certificado de otro
        cliente de AWS. Se elige la primera IP que hoy valide el certificado y
        se guarda en la config para que la proxima corrida no repita el salto.
        """

        net.flush_dns()
        ip = net.valid_ip(self.host, self._port, min(self.timeout, 5.0))
        self.pin_ip = ip
        if ip:
            net.save_pin(self._pinned_path, self.host, ip)
        else:
            net.drop_pin(self._pinned_path)
        return bool(ip)

    def send(self, request: Request):
        """Hace el pedido con la pausa y el pin vigente.

        Mapea los errores de red a ``CampusError`` y, si el certificado es de
        otro sitio, prueba otra IP una sola vez.
        """

        return self._send(request, rerouted=False)

    def _send(self, request: Request, *, rerouted: bool):
        self._wait()
        try:
            return self._opener.open(request, timeout=self.timeout)
        except HTTPError as exc:
            raise CampusHTTPError(f"El campus respondio HTTP {exc.code}.", exc.code) from exc
        except URLError as exc:
            if not rerouted and net.cert_mismatch(exc) and self._route_around():
                return self._send(request, rerouted=True)
            if not rerouted and self.pin_ip:
                # La IP recordada dejo de responder: se descarta y se reintenta
                # una vez sin pin en vez de fallar el comando.
                self.pin_ip = ""
                net.drop_pin(self._pinned_path)
                return self._send(request, rerouted=True)
            self.pin_ip = ""
            if net.cert_mismatch(exc):
                raise CampusError(
                    "No se pudo conectar con el campus: el servidor presento el "
                    f"certificado de otro sitio ({exc.reason}). Vuelve a intentarlo; "
                    "si insiste, limpia la cache DNS con: ipconfig /flushdns"
                ) from exc
            raise CampusError(f"No se pudo conectar con el campus: {exc.reason}.") from exc
        except ssl.SSLCertVerificationError as exc:
            if not rerouted and self._route_around():
                return self._send(request, rerouted=True)
            raise CampusError(
                "No se pudo conectar con el campus: el servidor presento un "
                f"certificado de otro sitio ({exc}). Vuelve a intentarlo."
            ) from exc
        except TimeoutError as exc:
            raise CampusError("La conexion con el campus agoto el tiempo de espera.") from exc

    def close(self) -> None:
        try:
            self._opener.close()
        except Exception:  # noqa: BLE001 - el opener no siempre lo implementa
            pass
