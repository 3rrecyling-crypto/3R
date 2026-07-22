"""Cliente de IA minimalista y SIN dependencias de otros módulos de negocio.

Soporta dos proveedores:
  - "anthropic": SDK oficial de Anthropic (Claude).
  - "deepseek":  API OpenAI-compatible vía HTTP (requests), p. ej. https://api.deepseek.com

Es un helper puro texto→texto: no importa ni conoce facturación, viajes, etc.
Se usa tanto en los informes con IA como en el asistente 3D.
"""
from __future__ import annotations

import ipaddress
import json
import os
import socket
from typing import Optional
from urllib.parse import urlparse

import requests

# Defaults por entorno (fallback si no hay config por empresa).
# Modelo Anthropic por defecto: Claude Sonnet 5 (id exacto `claude-sonnet-5`,
# sin sufijo de fecha). Se puede sobreescribir por empresa (ia_modelo) o por
# la variable de entorno ANTHROPIC_MODEL.
DEFAULT_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
DEFAULT_DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEFAULT_DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")


class IAError(Exception):
    """Error legible para devolver al cliente (clave inválida, sin crédito, red…)."""


# ── Visión: fotos que el usuario sube a la IA ────────────────────────────────
_MEDIA_TYPES_OK = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGENES = 8  # tope defensivo de fotos por petición


def _parse_imagen(img) -> tuple[str, str]:
    """Normaliza una imagen a (media_type, base64) para la API de Anthropic.

    Acepta una data URL (`data:image/jpeg;base64,XXXX`), un dict
    `{"media_type": ..., "data": ...}`, o base64 pelado. Devuelve ('', '') si
    no es utilizable.
    """
    if isinstance(img, dict):
        mt = (img.get("media_type") or "image/jpeg").strip().lower()
        data = (img.get("data") or "").strip()
    else:
        s = str(img or "").strip()
        if s.startswith("data:"):
            try:
                header, data = s.split(",", 1)
                mt = header[5:].split(";")[0].strip().lower() or "image/jpeg"
                data = data.strip()
            except ValueError:
                return ("", "")
        else:
            mt, data = "image/jpeg", s  # base64 pelado, asumimos jpeg
    if mt == "image/jpg":
        mt = "image/jpeg"
    if mt not in _MEDIA_TYPES_OK or not data:
        return ("", "")
    return (mt, data)


def _bloques_imagen(imagenes) -> list:
    """Convierte la lista de imágenes en bloques de visión de Anthropic."""
    bloques = []
    for img in (imagenes or [])[:MAX_IMAGENES]:
        mt, data = _parse_imagen(img)
        if data:
            bloques.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mt, "data": data},
            })
    return bloques


def _url_externa_segura(base_url: str) -> bool:
    """Anti-SSRF: la URL base debe ser HTTPS y resolver SOLO a IPs públicas.
    Bloquea loopback/privadas/link-local (169.254.x, 127.x, 10.x, metadata…)."""
    try:
        p = urlparse(base_url)
    except Exception:
        return False
    if p.scheme != "https" or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


def _deepseek_chat(api_key: str, base_url: str, modelo: str, system: str, user: str,
                   max_tokens: int, temperature: float, json_mode: bool) -> str:
    base = base_url or DEFAULT_DEEPSEEK_BASE_URL
    if not _url_externa_segura(base):
        raise IAError("La URL base del proveedor de IA no es válida o apunta a una red interna. "
                      "Usa https://api.deepseek.com (o un host público con HTTPS).")
    url = base.rstrip("/") + "/chat/completions"
    body = {
        "model": modelo or DEFAULT_DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=120,
            allow_redirects=False,  # evita redirecciones a hosts internos (SSRF)
        )
    except requests.RequestException as e:
        raise IAError(f"No se pudo conectar con DeepSeek: {e}")
    if r.status_code >= 400:
        detalle = ""
        try:
            detalle = (r.json().get("error") or {}).get("message") or r.text[:300]
        except Exception:
            detalle = r.text[:300]
        raise IAError(f"DeepSeek respondió {r.status_code}: {detalle}")
    try:
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        raise IAError(f"Respuesta inesperada de DeepSeek: {e}")


def _ssl_context_ia():
    """SSLContext que confía en certifi MÁS una CA extra (variable de entorno
    IA_EXTRA_CA), para redes con antivirus/proxy que interceptan TLS (p. ej. Avast
    en Windows, que si no rompe la conexión con "Connection error"). Es análogo a
    NODE_EXTRA_CA_CERTS de Node. Devuelve None si IA_EXTRA_CA no está configurada,
    para usar el trust por defecto (p. ej. en producción)."""
    extra = os.environ.get("IA_EXTRA_CA", "").strip()
    if not extra or not os.path.exists(extra):
        return None
    import ssl
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    try:
        ctx.load_verify_locations(cafile=extra)
    except Exception:
        return None
    return ctx


def _anthropic_chat(api_key: str, modelo: str, system: str, user: str, max_tokens: int,
                    imagenes=None) -> str:
    try:
        import anthropic
    except ImportError:
        raise IAError("El paquete 'anthropic' no está instalado en el backend.")
    # Si hay fotos, el contenido del mensaje es una lista [imágenes..., texto].
    bloques = _bloques_imagen(imagenes)
    contenido = (bloques + [{"type": "text", "text": user}]) if bloques else user
    try:
        # En redes con antivirus/proxy que interceptan TLS, agrega su CA con IA_EXTRA_CA.
        _ctx = _ssl_context_ia()
        if _ctx is not None:
            import httpx
            client = anthropic.Anthropic(api_key=api_key, http_client=httpx.Client(verify=_ctx, timeout=120))
        else:
            client = anthropic.Anthropic(api_key=api_key)
        with client.messages.stream(
            model=modelo or DEFAULT_ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": contenido}],
            # Sin razonamiento extendido: estas tareas son extracción/generación de
            # JSON, no necesitan "thinking". Sonnet 5 lo trae ON por default y eso
            # disparaba la latencia a ~44s (timeout → "Error 500"). Apagado baja a
            # ~10-15s. Válido en Sonnet 5 / Opus 4.x (no usar en Fable 5).
            thinking={"type": "disabled"},
        ) as stream:
            mensaje = stream.get_final_message()
        return "".join(
            b.text for b in mensaje.content if getattr(b, "type", None) == "text"
        ).strip()
    except IAError:
        raise
    except Exception as e:
        raise IAError(getattr(e, "message", None) or str(e))


def chat_ia(proveedor: str, api_key: str, system: str, user: str, *,
            base_url: str = "", modelo: str = "",
            max_tokens: int = 4000, temperature: float = 0.4,
            json_mode: bool = False, imagenes=None) -> str:
    """Llama al proveedor configurado y devuelve el texto de la respuesta.

    `json_mode=True` pide al modelo responder JSON puro (soportado por DeepSeek;
    para Anthropic el prompt debe pedir JSON explícitamente).
    `imagenes` (opcional): lista de fotos (data URLs base64) que el usuario sube;
    solo se aprovechan con Anthropic (visión de Claude).
    Lanza IAError con un mensaje legible ante cualquier fallo.
    """
    if not api_key:
        raise IAError("Falta la API key del proveedor de IA.")
    # SEGURIDAD (defensa en profundidad): la API key del proveedor NUNCA debe ir
    # en el contenido enviado al modelo. Si por un bug apareciera en el prompt, se
    # redacta antes de mandarlo. Solo viaja en la cabecera Authorization del HTTP.
    if len(api_key) >= 12:
        system = system.replace(api_key, "[oculto]")
        user = user.replace(api_key, "[oculto]")
    prov = (proveedor or "anthropic").lower()
    if prov == "deepseek":
        if imagenes:
            raise IAError("Las fotos solo funcionan con el proveedor Anthropic (Claude). "
                          "Configura ANTHROPIC_API_KEY (e IA_PROVEEDOR=anthropic) en el .env del backend.")
        return _deepseek_chat(api_key, base_url, modelo, system, user,
                              max_tokens, temperature, json_mode)
    return _anthropic_chat(api_key, modelo, system, user, max_tokens, imagenes=imagenes)


def resolver_config_ia(empresa_id: Optional[int]) -> dict:
    """Resuelve (proveedor, api_key, base_url, modelo) desde ConfiguracionEmpresa
    con fallback a variables de entorno. NO toca ningún módulo de negocio.

    SEGURIDAD: la `base_url` provista por la empresa SOLO se usa junto con la
    llave de esa misma empresa. Si caemos a la llave COMPARTIDA del backend
    (variable de entorno), se fuerza la URL por defecto de confianza, para que
    la llave compartida nunca se envíe a un host arbitrario del cliente.
    """
    proveedor, api_key, base_url, modelo = "anthropic", "", "", ""
    # 3r single-tenant: la config de IA vive en el singleton ConfiguracionSistema
    # (panel Configuración → IA). El `empresa_id` se ignora (no hay modelo Empresa).
    try:
        from api.models import ConfiguracionSistema
        cfg = ConfiguracionSistema.get_config()
        proveedor = (cfg.ia_proveedor or "anthropic").strip().lower()
        base_url = (cfg.ia_base_url or "").strip()
        modelo = (cfg.ia_modelo or "").strip()
        if (cfg.ia_api_key or "").strip():
            api_key = cfg.ia_api_key.strip()
    except Exception:
        pass
    if not api_key:
        # Fallback a la llave compartida del backend → base_url de confianza.
        if proveedor == "deepseek":
            api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            base_url = DEFAULT_DEEPSEEK_BASE_URL
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            base_url = ""  # Anthropic ignora base_url
    return {"proveedor": proveedor, "api_key": api_key, "base_url": base_url, "modelo": modelo}
