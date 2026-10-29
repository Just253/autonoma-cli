"""Cifrado con DPAPI (solo Windows)."""

from __future__ import annotations

import ctypes
import os

try:  # ctypes.wintypes solo existe en Windows
    from ctypes import wintypes
except ImportError:  # pragma: no cover - plataformas sin wintypes
    wintypes = None  # type: ignore[assignment]

CRYPTPROTECT_UI_FORBIDDEN = 0x01

if wintypes is not None:

    class _DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data, len(data))
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))


def _protect(data: bytes) -> bytes:
    """Cifra con DPAPI. Solo disponible en Windows."""

    if os.name != "nt":
        raise OSError("DPAPI solo existe en Windows")
    blob_in = _blob(data)
    blob_out = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "autonoma-cli",
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptProtectData fallo")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _unprotect(data: bytes) -> bytes:
    """Descifra con DPAPI. Solo disponible en Windows."""

    if os.name != "nt":
        raise OSError("DPAPI solo existe en Windows")
    blob_in = _blob(data)
    blob_out = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(blob_out),
    )
    if not ok:
        raise OSError("CryptUnprotectData fallo")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
