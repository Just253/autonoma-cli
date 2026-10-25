"""Excepciones propias del cliente del campus.

Se separan por tipo para que la CLI pueda dar mensajes utiles: no es lo mismo
una contrasena incorrecta que una sesion vencida o un endpoint que cambio.
"""

from __future__ import annotations


class AutonomaError(Exception):
    """Error base del proyecto."""


class CampusError(AutonomaError):
    """Problema de red o de respuesta del campus."""


class AuthenticationError(CampusError):
    """El campus rechazo las credenciales."""


class SessionExpiredError(CampusError):
    """La cookie del campus dejo de ser valida."""


class ProtocolError(CampusError):
    """La respuesta no tiene el formato esperado."""


class CampusHTTPError(CampusError):
    """Respuesta HTTP con codigo relevante (se conserva para reintentos)."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class UsageError(AutonomaError):
    """Error de uso que la CLI muestra sin traza de pila."""
