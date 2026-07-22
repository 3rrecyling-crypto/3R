"""Validación OFFLINE de claves de licencia PREMIUM.

Formato de clave:  SANB-XXXXX-XXXXX-XXXXX  (X = A-Z / 2-9, sin 0/O/1/I)
Los primeros 13 caracteres del cuerpo son aleatorios; los últimos 2 son la suma
de verificación (base32 del hash ponderado del cuerpo con una sal fija).

No requiere internet ni servidor de licencias: la clave "trae" su validez.
Las claves se generan con `python manage.py generar_licencias [n]`.
"""
from __future__ import annotations

import re
import secrets

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # sin 0/O/1/I (evita confusiones)
_SAL = "SANBENITO-PREMIUM-2026"
_RE_CLAVE = re.compile(r"^SANB-([A-Z2-9]{5})-([A-Z2-9]{5})-([A-Z2-9]{5})$")


def _checksum(cuerpo13: str) -> str:
    """Dos caracteres de verificación para los 13 del cuerpo."""
    total = 0
    mezcla = cuerpo13 + _SAL
    for i, ch in enumerate(mezcla):
        total = (total * 31 + ord(ch) * (i + 7)) % (32 * 32)
    return ALFABETO[total // 32] + ALFABETO[total % 32]


def clave_valida(clave: str) -> bool:
    c = (clave or "").strip().upper().replace(" ", "")
    m = _RE_CLAVE.match(c)
    if not m:
        return False
    cuerpo = "".join(m.groups())
    return cuerpo[13:] == _checksum(cuerpo[:13])


def normalizar(clave: str) -> str:
    return (clave or "").strip().upper().replace(" ", "")


def generar_clave() -> str:
    cuerpo13 = "".join(secrets.choice(ALFABETO) for _ in range(13))
    cuerpo = cuerpo13 + _checksum(cuerpo13)
    return f"SANB-{cuerpo[0:5]}-{cuerpo[5:10]}-{cuerpo[10:15]}"
