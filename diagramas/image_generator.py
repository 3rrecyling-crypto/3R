"""
Servicio de generación de imágenes para Canvas Pro.

Estrategia de generación (en orden):
  1. Google Gemini — solo si la empresa tiene key Y facturación activa (las
     imágenes de Gemini NO están en la capa gratis: dan cuota 0 sin billing).
  2. Pollinations.ai — GRATIS, sin API key, sin facturación. Fallback siempre
     disponible para que el botón funcione aunque no haya key de Gemini.

Además, si la empresa tiene key de Claude/DeepSeek configurada, se usa para
enriquecer el prompt antes de generar (Claude/DeepSeek NO crean imágenes; solo
mejoran el texto del prompt).

Todas las credenciales se leen del panel de admin (ConfiguracionEmpresa), con
fallback a variables de entorno.
"""
import base64
import logging
import os
import urllib.parse
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Endpoint público y gratuito de Pollinations (sin API key).
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/"

# Modelos de Gemini capaces de generar imágenes (via generate_content con la
# modalidad IMAGE). Los nombres cambian con el tiempo, así que probamos en orden
# y usamos el primero que responda con una imagen. Se puede forzar uno desde el
# panel (campo imagen_modelo) y se prueba primero. Si TODOS fallan, se descubren
# dinámicamente con client.models.list() (ver _descubrir_modelos_imagen).
GEMINI_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image",
]


def _descubrir_modelos_imagen(client) -> list:
    """
    Consulta a la API los modelos reales disponibles y devuelve los que pueden
    generar imágenes (nombre contiene 'image' y soportan generateContent).
    Auto-cura el servicio si Google renombra los modelos.
    """
    encontrados = []
    try:
        for m in client.models.list():
            nombre = (m.name or "").replace("models/", "")
            acciones = list(getattr(m, "supported_actions", None) or [])
            if "image" in nombre.lower() and "generateContent" in acciones:
                encontrados.append(nombre)
    except Exception as e:
        logger.warning("No se pudieron listar modelos de Gemini: %s", e)
    return encontrados


def _resolver_credenciales(empresa_id: Optional[int]) -> Tuple[str, str, str, str, str]:
    """
    Lee del panel de admin (ConfiguracionEmpresa) las credenciales necesarias.

    Devuelve: (imagen_api_key, imagen_modelo, texto_api_key, texto_proveedor, texto_modelo)
    Si no hay empresa_id, usa la primera configuración (conveniencia mono-empresa).
    """
    # 3r: credenciales del panel Configuración → IA (singleton ConfiguracionSistema)
    # con fallback a variables de entorno del backend.
    import os
    imagen_key = imagen_modelo = texto_key = texto_modelo = ""
    proveedor = "anthropic"
    try:
        from api.models import ConfiguracionSistema
        cfg = ConfiguracionSistema.get_config()
        imagen_key = (cfg.imagen_api_key or "").strip()
        imagen_modelo = (cfg.imagen_modelo or "").strip()
        texto_key = (cfg.ia_api_key or "").strip()
        proveedor = (cfg.ia_proveedor or "anthropic").strip().lower()
        texto_modelo = (cfg.ia_modelo or "").strip()
    except Exception:
        pass
    if not imagen_key:
        imagen_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("IMAGEN_API_KEY") or "").strip()
    if not imagen_modelo:
        imagen_modelo = (os.environ.get("IMAGEN_MODELO") or "").strip()
    if not texto_key:
        texto_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        proveedor = (os.environ.get("IA_PROVEEDOR") or proveedor or "anthropic").strip().lower()
    if not texto_modelo:
        texto_modelo = (os.environ.get("IA_MODELO") or "").strip()
    return (imagen_key, imagen_modelo, texto_key, proveedor, texto_modelo)


def _mejorar_prompt(prompt: str, texto_api_key: str, proveedor: str, modelo: str) -> str:
    """
    Enriquecer el prompt con Claude (si la empresa tiene key de Anthropic).
    Si falla o no hay key, cae a añadir palabras clave de calidad. Nunca lanza.
    """
    base = (prompt or "").strip()
    if proveedor == "anthropic" and texto_api_key:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=texto_api_key)
            resp = client.messages.create(
                model=modelo or "claude-3-5-sonnet-20241022",
                max_tokens=220,
                messages=[{
                    "role": "user",
                    "content": (
                        "Reescribe el siguiente pedido como un prompt de generación de "
                        "imagen en INGLÉS: detallado y visual (colores, estilo, composición, "
                        "iluminación, calidad). Devuelve SOLO el prompt, sin comillas ni "
                        f"explicaciones.\n\nPedido: {base}"
                    ),
                }],
            )
            txt = (resp.content[0].text or "").strip()
            if txt:
                return txt
        except Exception as e:
            logger.warning("No se pudo mejorar el prompt con Claude (se usa directo): %s", e)
    # Fallback sin llamadas externas: keywords de calidad.
    return f"{base}, high quality, highly detailed, professional, sharp focus, 4k"


def _generar_con_pollinations(prompt: str, width: int = 768, height: int = 768,
                              seed: Optional[int] = None) -> str:
    """
    Genera una imagen con Pollinations.ai (GRATIS, sin API key).
    Devuelve la imagen como data URL (base64). Lanza en caso de error de red.
    """
    encoded = urllib.parse.quote(prompt, safe="")
    params = {"width": width, "height": height, "nologo": "true", "model": "flux"}
    if seed is not None:
        params["seed"] = seed
    url = POLLINATIONS_URL + encoded + "?" + urllib.parse.urlencode(params)

    resp = requests.get(url, timeout=90)
    resp.raise_for_status()

    content_type = resp.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise ValueError("Pollinations no devolvió una imagen (respuesta inesperada).")

    b64 = base64.b64encode(resp.content).decode("utf-8")
    logger.info("Imagen generada con Pollinations (%d bytes)", len(resp.content))
    return f"data:{content_type};base64,{b64}"


def _generar_con_gemini(prompt: str, api_key: str, modelo_forzado: str = "") -> str:
    """
    Genera una imagen con Gemini y la devuelve como data URL (base64).
    Prueba varios modelos hasta que uno responda con imagen.
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise ValueError("google-genai no está instalado. Ejecuta: pip install google-genai")

    client = genai.Client(api_key=api_key)

    # Orden: modelo forzado (panel) → lista conocida → descubrimiento dinámico.
    modelos = ([modelo_forzado] if modelo_forzado else [])
    modelos += [m for m in GEMINI_IMAGE_MODELS if m != modelo_forzado]

    ultimo_error = None
    intentados = set()
    descubrio = False

    while modelos:
        modelo = modelos.pop(0)
        if modelo in intentados:
            continue
        intentados.add(modelo)
        try:
            resp = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
            )
            for cand in (resp.candidates or []):
                content = getattr(cand, "content", None)
                for part in (getattr(content, "parts", None) or []):
                    inline = getattr(part, "inline_data", None)
                    if inline is not None and getattr(inline, "data", None):
                        mime = getattr(inline, "mime_type", None) or "image/png"
                        b64 = base64.b64encode(inline.data).decode("utf-8")
                        logger.info("Imagen generada con modelo %s (%d bytes)", modelo, len(inline.data))
                        return f"data:{mime};base64,{b64}"
            # No hubo imagen: quizá bloqueo de seguridad o solo texto.
            ultimo_error = ValueError(f"El modelo {modelo} no devolvió una imagen.")
            logger.warning("Modelo %s no devolvió imagen, probando siguiente.", modelo)
        except Exception as e:
            ultimo_error = e
            logger.warning("Fallo con modelo %s: %s", modelo, e)
            # Cuota 0 / sin facturación: TODOS los modelos darán lo mismo.
            # Cortamos ya para caer rápido al fallback gratis (Pollinations).
            emsg = str(e)
            if "RESOURCE_EXHAUSTED" in emsg or "429" in emsg or "billing" in emsg.lower():
                raise ValueError("Gemini sin cuota de imágenes (requiere facturación).")

        # Si agotamos la lista conocida y aún no funcionó, descubrir dinámicamente.
        if not modelos and not descubrio:
            descubrio = True
            nuevos = [m for m in _descubrir_modelos_imagen(client) if m not in intentados]
            if nuevos:
                logger.info("Descubrimiento dinámico de modelos de imagen: %s", nuevos)
                modelos.extend(nuevos)

    # Ningún modelo funcionó.
    msg = str(ultimo_error) if ultimo_error else "desconocido"
    raise ValueError(f"Gemini no pudo generar la imagen: {msg}")


def generar_imagen_ai(prompt_usuario: str, empresa_id: Optional[int] = None,
                      width: int = 768, height: int = 768,
                      seed: Optional[int] = None) -> Optional[str]:
    """
    Pipeline completo:
      1. (opcional) mejora el prompt con Claude/DeepSeek de la empresa.
      2. intenta Gemini si hay key (premium, requiere facturación).
      3. cae a Pollinations.ai (GRATIS) si Gemini no está o falla.
    `seed` produce variaciones distintas del mismo prompt (para "generar 4 opciones").
    Retorna data URL de la imagen o lanza ValueError con mensaje claro.
    """
    imagen_key, imagen_modelo, texto_key, proveedor, texto_modelo = _resolver_credenciales(empresa_id)

    # Fallback a entorno para la key de Gemini.
    if not imagen_key:
        imagen_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

    # 1. Enriquecer el prompt (usa la key de Claude/DeepSeek si existe).
    prompt_final = _mejorar_prompt(prompt_usuario, texto_key, proveedor, texto_modelo)
    logger.info("Generando imagen. Prompt final: %s", prompt_final)

    # 2. Intentar Gemini (mejor calidad) si hay key configurada.
    if imagen_key:
        try:
            # Variaciones en Gemini: se sugiere una variante distinta en el prompt.
            p = prompt_final if seed is None else f"{prompt_final} (variación única #{seed})"
            return _generar_con_gemini(p, imagen_key, imagen_modelo)
        except Exception as e:
            logger.warning("Gemini no disponible (%s). Usando Pollinations (gratis).", e)

    # 3. Fallback GRATIS: Pollinations (sin key, sin facturación).
    try:
        return _generar_con_pollinations(prompt_final, width, height, seed=seed)
    except Exception as e:
        raise ValueError(f"No se pudo generar la imagen (Pollinations): {e}")
