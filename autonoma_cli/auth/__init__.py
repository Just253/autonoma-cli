"""Autenticacion del campus: formulario, cookies y sesion autenticada."""

from __future__ import annotations

from .cookies import CookieStore
from .form import (
    LOGIN_REDIRECT,
    LoginOutcome,
    LoginPageParser,
    build_login_data,
    classify_login,
    student_code_from_html,
)
from .session import AuthSession, Transport

__all__ = [
    "AuthSession",
    "CookieStore",
    "LOGIN_REDIRECT",
    "LoginOutcome",
    "LoginPageParser",
    "Transport",
    "build_login_data",
    "classify_login",
    "student_code_from_html",
]
