"""Envío de recordatorios por canales externos: WhatsApp (Twilio) y correo.

Config en el `.env` (como el resto de secrets):

    TWILIO_ACCOUNT_SID=ACxxxxxxxx
    TWILIO_AUTH_TOKEN=xxxxxxxx
    TWILIO_WHATSAPP_FROM=whatsapp:+14155238886   # tu número de WhatsApp de Twilio

El correo usa la configuración EMAIL_* de Django (SMTP). Todo es best-effort: si
falta config o falla el envío, NO rompe nada (el aviso en el chat igual se manda).
"""
from __future__ import annotations

import os
import re


def _twilio_cfg():
    return (
        (os.environ.get("TWILIO_ACCOUNT_SID") or "").strip(),
        (os.environ.get("TWILIO_AUTH_TOKEN") or "").strip(),
        (os.environ.get("TWILIO_WHATSAPP_FROM") or "").strip(),
    )


def whatsapp_configurado() -> bool:
    sid, token, frm = _twilio_cfg()
    return bool(sid and token and frm)


def _norm_wa(numero: str) -> str:
    """Normaliza a `whatsapp:+<num>`. Si no trae lada y son 10 dígitos, asume MX."""
    n = (numero or "").strip()
    if not n:
        return ""
    if n.startswith("whatsapp:"):
        return n
    n = re.sub(r"[^\d+]", "", n)
    if not n.startswith("+"):
        n = ("+52" + n) if len(n) == 10 else ("+" + n)
    return f"whatsapp:{n}"


def enviar_whatsapp(telefono: str, texto: str) -> bool:
    if not whatsapp_configurado() or not telefono:
        return False
    sid, token, frm = _twilio_cfg()
    try:
        from twilio.rest import Client
        Client(sid, token).messages.create(from_=frm, to=_norm_wa(telefono), body=texto)
        return True
    except Exception:
        return False


def enviar_correo(correos, asunto: str, texto: str) -> bool:
    destinatarios = [c for c in (correos if isinstance(correos, (list, tuple)) else [correos]) if c]
    if not destinatarios:
        return False
    try:
        from django.conf import settings
        from django.core.mail import send_mail
        remitente = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@3recycling.com.mx"
        send_mail(asunto, texto, remitente, destinatarios, fail_silently=True)
        return True
    except Exception:
        return False


def enviar_recordatorio_externo(evento, texto: str) -> str:
    """Despacha el recordatorio por el canal del evento. Devuelve el canal usado
    ('WHATSAPP'/'CORREO') o '' si no se pudo enviar."""
    canal = getattr(evento, "canal_recordatorio", "CHAT")
    destino = (getattr(evento, "recordatorio_destino", "") or "").strip()
    asunto = f"Recordatorio: {evento.titulo}"
    if canal == "WHATSAPP":
        if enviar_whatsapp(destino, texto):
            return "WHATSAPP"
    elif canal == "CORREO":
        correos = [destino] if destino else [
            u.email for u in evento.participantes.all() if getattr(u, "email", "")
        ]
        if enviar_correo(correos, asunto, texto):
            return "CORREO"
    return ""
