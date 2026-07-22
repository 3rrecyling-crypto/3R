"""Asistentes IA para Diagramas (flujogramas) y Canvas (diseño).

Cada asistente convierte el pedido del cliente (texto) en un PLAN JSON validado
que el editor del frontend dibuja. Aislamiento: SOLO conoce el catálogo de su
editor y el cliente de IA (ia_studio.ia_client); NO importa facturación ni ningún
otro módulo de negocio.
"""
from __future__ import annotations

import base64
import json
import math
import re
from typing import Optional

from ia_studio.ia_client import IAError, chat_ia


class _PlanError(Exception):
    """Error legible cuando el plan no es utilizable."""


# ── Motor de texto GEMINI (gratis) ────────────────────────────────────────────
# El texto de Gemini SÍ tiene capa gratuita (a diferencia de las imágenes) y
# soporta visión. Se usa como motor de los asistentes del Canvas cuando la
# empresa tiene key de Gemini configurada, sin depender de Claude/DeepSeek.
GEMINI_TEXT_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.0-flash-001"]


def _gemini_text(api_key: str, system: str, user: str, imagenes=None,
                 temperature: float = 0.3) -> str:
    from google import genai
    from google.genai import types

    # Timeout duro (ms): evita que una llamada colgada bloquee el worker ASGI
    # (Daphne) indefinidamente. Si Gemini no responde en 40s, falla limpio.
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=40000))
    partes = []
    for img in (imagenes or [])[:1]:  # solo 1 imagen (visión): menos peso, más rápido
        s = str(img or "")
        if s.startswith("data:") and "," in s:
            try:
                header, data = s.split(",", 1)
                mime = header[5:].split(";")[0] or "image/png"
                partes.append(types.Part.from_bytes(data=base64.b64decode(data), mime_type=mime))
            except Exception:
                pass
    partes.append(types.Part.from_text(text=user))

    # Config base. Desactivar "thinking" acelera MUCHO (los flash 2.5/3.x razonan
    # por defecto y eso dispara la latencia a ~20-25s); para generar JSON de
    # diseño no hace falta. Si el modelo no soporta thinking_config, se reintenta
    # sin ese campo (cfg_simple).
    common = dict(system_instruction=system, temperature=temperature,
                  response_mime_type="application/json", max_output_tokens=3000)
    try:
        cfg_fast = types.GenerateContentConfig(
            **common, thinking_config=types.ThinkingConfig(thinking_budget=0))
    except Exception:
        cfg_fast = None
    cfg_simple = types.GenerateContentConfig(**common)

    ultimo = None
    for modelo in GEMINI_TEXT_MODELS:
        for cfg in ([cfg_fast, cfg_simple] if cfg_fast else [cfg_simple]):
            try:
                r = client.models.generate_content(model=modelo, contents=partes, config=cfg)
                if r and r.text:
                    return r.text
                ultimo = ValueError(f"respuesta vacía de {modelo}")
                break  # respuesta vacía: pasar al siguiente modelo
            except Exception as e:
                ultimo = e
                msg = str(e)
                # Sin cuota / modelo inexistente: NO reintentar config (es instantáneo),
                # saltar YA al siguiente modelo. Solo reintentamos cfg_simple si el
                # fallo pudo ser por thinking_config no soportado.
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg or "NOT_FOUND" in msg or "404" in msg:
                    break
                continue
    raise IAError(f"Gemini (texto) no disponible: {ultimo}")


GEMINI_IMAGE_MODELS = ["gemini-2.5-flash-image", "gemini-2.5-flash-image-preview",
                       "gemini-2.0-flash-preview-image-generation"]


def generar_imagen(pedido: str, cfg: dict, imagenes=None, contexto: str = "",
                   gemini_key: str = "") -> dict:
    """Genera UNA imagen con Gemini (nano banana) a partir de la descripción.
    Devuelve {'imagen': 'data:image/png;base64,...'}. Requiere key de Gemini
    (Claude no genera imágenes)."""
    if not gemini_key:
        raise _PlanError("Para generar fotos se necesita una API key de GEMINI (gratis). "
                         "Pide al administrador que configure GEMINI_API_KEY en el .env del backend.")
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=gemini_key, http_options=types.HttpOptions(timeout=60000))
    prompt = (pedido or "").strip()[:1500]
    if contexto and contexto.strip():
        prompt += f"\n\nContexto: {contexto.strip()[:500]}"
    ultimo = None
    for modelo in GEMINI_IMAGE_MODELS:
        try:
            r = client.models.generate_content(
                model=modelo,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            for cand in (r.candidates or []):
                for parte in (getattr(cand.content, "parts", None) or []):
                    inline = getattr(parte, "inline_data", None)
                    if inline is not None and getattr(inline, "data", None):
                        raw = inline.data
                        b64 = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
                        # el SDK puede entregar bytes crudos o base64: normaliza a base64
                        try:
                            base64.b64decode(b64, validate=True)
                        except Exception:
                            b64 = base64.b64encode(raw if isinstance(raw, (bytes, bytearray)) else raw.encode()).decode()
                        mime = getattr(inline, "mime_type", "") or "image/png"
                        return {"imagen": f"data:{mime};base64,{b64}"}
            ultimo = ValueError(f"{modelo} no devolvió imagen")
        except Exception as e:  # noqa: BLE001
            ultimo = e
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                continue
    raise IAError(f"No se pudo generar la imagen con Gemini: {ultimo}")


def llamar_ia_texto(cfg: dict, gemini_key: str, system: str, user: str, *,
                    imagenes=None, temperature: float = 0.3, max_tokens: int = 6000) -> str:
    """Elige el motor de texto: Gemini (gratis) si hay key; si no, Claude/DeepSeek."""
    if gemini_key:
        return _gemini_text(gemini_key, system, user, imagenes=imagenes, temperature=temperature)
    return chat_ia(
        proveedor=cfg["proveedor"], api_key=cfg["api_key"], base_url=cfg["base_url"],
        modelo=cfg["modelo"], system=system, user=user,
        max_tokens=max_tokens, temperature=temperature, json_mode=True, imagenes=imagenes,
    )


# ── Helpers compartidos ───────────────────────────────────────────────────────
def _extraer_json(txt: str) -> Optional[dict]:
    if not txt:
        return None
    s = txt.strip()
    s = re.sub(r"^```(?:json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
    try:
        d = json.loads(s)
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        try:
            d = json.loads(s[i:j + 1])
            return d if isinstance(d, dict) else None
        except Exception:
            return None
    return None


def _num(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _lst(v):
    """Devuelve v si es lista; si el modelo mandó otra cosa (dict/int/str),
    devuelve [] para que caiga en el _PlanError amable (422) en vez de un 500."""
    return v if isinstance(v, list) else []


_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _color(v, default: Optional[str]) -> Optional[str]:
    s = str(v or "").strip()
    if s.lower() == "none":
        return "none"
    if _HEX.match(s):
        return s
    return default


# ══════════════════════════════ DIAGRAMAS ════════════════════════════════════
SHAPE_KINDS = {
    "oval", "rect", "rounded", "diamond", "parallelogram", "document", "predefined",
    "manual", "trapezoid", "delay", "display", "cylinder", "card", "circle",
    "hexagon", "triangle", "note", "text",
}

SYSTEM_PROMPT_DIAGRAMA = f"""Eres un experto en modelado de procesos que diseña DIAGRAMAS DE FLUJO profesionales (estilo BPMN/ISO 9001) a partir del pedido del cliente, en español.

Tu única salida es un objeto JSON con este esquema EXACTO (sin texto adicional, sin markdown):
{{
  "titulo": "<título corto del proceso>",
  "nodes": [ {{ "id": "n1", "tipo": "<forma>", "label": "<texto del nodo>", "x": <número>, "y": <número> }} ],
  "edges": [ {{ "source": "<id nodo>", "target": "<id nodo>", "label": "<opcional: Sí/No/…>" }} ]
}}

Formas válidas (campo "tipo") — ELIGE la correcta, no uses "rect" para todo:
- oval = Inicio / Fin (terminal)
- rect = Proceso (acción) · rounded = Proceso · predefined = Subproceso · manual = Operación manual · trapezoid = Operación
- diamond = Decisión (SIEMPRE con 2+ salidas etiquetadas "Sí"/"No" o condiciones)
- parallelogram = Datos / Entrada-Salida · document = Documento o registro (formato, acta, reporte)
- display = Pantalla/sistema · cylinder = Base de datos · delay = Demora / espera
- circle = Conector · hexagon · triangle · card = Tarjeta · note = Nota · text = Texto suelto
(Cualquier otro tipo se convierte a "rect".)

LAYOUT PROFESIONAL (clave para que se vea limpio; el sistema colorea por tipo):
- Flujo PRINCIPAL en una columna vertical: usa x=0 para esa columna y baja y en pasos de 150 (y=0,150,300,…). Los nodos miden ~180×70, así que 150 de separación deja aire.
- Alinea TODO a una rejilla: x múltiplo de 160 (…, -320, -160, 0, 160, 320) e y múltiplo de 150. NUNCA pongas dos nodos en la misma coordenada (jamás se encimen).
- Decisiones: la salida "Sí" continúa hacia ABAJO en la misma columna; la salida "No" va a una columna a la DERECHA (x=+320) y luego reingresa al flujo con un edge, o termina en su propio "Fin".
- Empieza con "oval" (Inicio) y cierra cada rama con "oval" (Fin).
- Etiquetas CORTAS y en verbo (≤6 palabras): "Registrar solicitud", "Validar documentación", "Notificar rechazo".
- Tamaño ideal: 8 a 18 nodos. Incluye los DOCUMENTOS/registros clave del proceso como nodos "document" (en ISO 9001 son la evidencia).
- Cada nodo con "id" ÚNICO (n1, n2, …). Cada edge referencia ids existentes con "source" y "target"; conecta el flujo completo (sin nodos sueltos).

Si el pedido es un procedimiento ISO 9001, refleja la secuencia real (solicitud → revisión → aprobación/rechazo → registro), con sus decisiones y evidencias.

Responde ÚNICAMENTE con el JSON."""


def validar_diagrama(raw: dict) -> dict:
    ids: set[str] = set()
    nodes = []
    for n in _lst(raw.get("nodes"))[:150]:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        if not nid or nid in ids:
            continue
        tipo = str(n.get("tipo") or n.get("shape") or "rect").strip()
        if tipo not in SHAPE_KINDS:
            tipo = "rect"
        ids.add(nid)
        nodes.append({
            "id": nid, "tipo": tipo,
            "label": str(n.get("label") or "").strip()[:220],
            "x": round(_clamp(_num(n.get("x")), -4000, 4000), 1),
            "y": round(_clamp(_num(n.get("y")), -4000, 4000), 1),
        })
    edges = []
    seen = set()
    for e in _lst(raw.get("edges"))[:400]:
        if not isinstance(e, dict):
            continue
        s = str(e.get("source") or "").strip()
        t = str(e.get("target") or "").strip()
        if s not in ids or t not in ids:
            continue
        key = (s, t, str(e.get("label") or ""))
        if key in seen:
            continue
        seen.add(key)
        edges.append({"source": s, "target": t, "label": str(e.get("label") or "").strip()[:60]})
    return {"titulo": str(raw.get("titulo") or "").strip()[:120], "nodes": nodes, "edges": edges}


def generar_diagrama(pedido: str, cfg: dict, imagenes=None, contexto: str = "",
                     gemini_key: str = "") -> dict:
    user = f"Pedido del cliente:\n{pedido.strip()}"
    if contexto:
        user += f"\n\nDATOS REALES para incorporar al diagrama:\n{contexto[:4000]}"
    if imagenes:
        user += ("\n\nEl cliente adjuntó FOTOS de referencia (un boceto, un proceso en "
                 "pizarrón, un formato). Conviértelas en el diagrama.")
    texto = llamar_ia_texto(cfg, gemini_key, SYSTEM_PROMPT_DIAGRAMA, user,
                            imagenes=imagenes, temperature=0.4, max_tokens=6000)
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió un diagrama válido. Reformula tu pedido.")
    plan = validar_diagrama(raw)
    if not plan["nodes"]:
        raise _PlanError("La IA no propuso nodos. Sé más específico (p. ej. 'proceso de compras con aprobación').")
    return plan


# ══════════════════════════════ CANVAS ═══════════════════════════════════════
CANVAS_SHAPES = {
    "rect", "ellipse", "diamond", "triangle", "star", "hexagon", "speech", "chevron",
    "parallelogram", "cloud", "semicircle", "ring",
}
CANVAS_TIPOS = CANVAS_SHAPES | {"line", "arrow", "text", "sticky", "frame", "foto"}

SYSTEM_PROMPT_CANVAS = f"""Eres un director de arte que compone diseños gráficos PROFESIONALES (estilo Figma/Canva) a partir del pedido del cliente, en español.

Tu única salida es un objeto JSON con este esquema EXACTO (sin texto adicional, sin markdown):
{{
  "fondo": "#RRGGBB",              // opcional, color de fondo del lienzo
  "artboard": {{ "w": 1080, "h": 1080 }},  // opcional, tamaño del área de diseño
  "elementos": [
    {{ "tipo": "<tipo>", "x": <n>, "y": <n>, "w": <n>, "h": <n>, "fill": "#RRGGBB", "stroke": "#RRGGBB", "sw": <n>, ... }}
  ]
}}

Tipos válidos: rect, ellipse, diamond, triangle, star, hexagon, speech, chevron, parallelogram, cloud, semicircle, ring, line, arrow, text, sticky, frame, foto.
Campos por tipo:
- foto: FOTOGRAFÍA REAL generada por IA. Campos: x,y,w,h y "prompt" (descripción DETALLADA en español: sujeto, estilo fotográfico, iluminación, encuadre, fondo). REGLA DE ORO: si el diseño incluye objetos/escenas del mundo real (personas, camiones, productos, comida, paisajes, maquinaria…), usa "foto" — NUNCA los imites con figuras geométricas. Máximo 2 por diseño; intégralas a la composición (p. ej. un rect con shadow como marco detrás).
- Formas (rect…ring): x,y,w,h + fill, stroke, sw. Opcionales: rx (radio esquinas), grad (2º color de degradado), shadow (bool), rot (grados), op/fillOp (0.1-1), dash (solid|dashed|dotted).
- text: x,y,w,h, "text" (obligatorio), fs (tamaño 14-140), bold, italic, talign (l|c|r), font (sans|serif|mono|hand). Para texto usa fill:"none", stroke = color del texto, sw:0.
- sticky: nota; x,y,w,h, "text", fill = color del papel.
- line / arrow: x,y,w,h y "points": [[0,0],[dx,dy]] (relativos a x,y, mínimo 2 puntos), stroke, sw.
- frame: área/mesa de trabajo x,y,w,h con "text" (nombre).

Reglas de calidad:
- Trabaja dentro de un lienzo ~1080×1080 (o el artboard indicado): x,y >= 0 y dentro del área.
- Composición profesional: jerarquía visual (título grande, subtítulos, cuerpo), buen contraste, alineación y aire. Paleta armónica (2-4 colores).
- Coloca primero los fondos/formas grandes y luego el texto encima (el orden del arreglo = orden de capas, lo último va arriba).
- Colores en hex #RRGGBB. Usa "none" para relleno o trazo cuando aplique.

DISEÑO DE ALTO IMPACTO (obligatorio — el resultado debe SORPRENDER, no parecer un borrador):
- CONTENCIÓN ESTRICTA: TODO elemento (incluidas las formas decorativas) debe quedar COMPLETAMENTE dentro del artboard: x>=0, y>=0, x+w<=W, y+h<=H. El lienzo NO recorta: lo que se sale del área se ve flotando suelto y arruina la pieza. Para el efecto de "forma cortada por el borde" usa un semicircle pegado al borde o una forma que TOQUE el margen sin salirse.
- Fondo con intención: color pleno + 2-4 formas decorativas GRANDES y suaves detrás del contenido (círculos/anillos/semicírculos con "fillOp" 0.10-0.30, o con "grad") para dar profundidad — siempre DENTRO del área. Nada de lienzo blanco vacío.
- Si el diseño incluye un marco/hueco pensado para una imagen, DEBES emitir el elemento "foto" correspondiente ocupando ese hueco (nunca dejes el marco vacío). Anuncios, pósters y piezas de reclutamiento llevan SIEMPRE al menos una foto real relevante.
- Degradados ("grad") en el bloque protagonista y en botones/cintas; puedes fijar "gradAngle" (0-360) o "gradType":"radial" para más carácter; "shadow": true en tarjetas y elementos que floten; esquinas redondeadas generosas (rx 16-28) en tarjetas.
- Legibilidad del texto sobre fotos/fondos con color: usa "highlight":"#RRGGBB" (caja detrás del texto) o pon el texto sobre un "rect". "underline"/"strike" cuando aporten.
- Tipografía con carácter: título 64-120 bold (talign "c" si es pieza centrada), subtítulo 28-40, cuerpo 18-24; sw:0 SIEMPRE en textos. Combina "sans" con un acento "serif" o "hand" cuando el tema lo permita.
- Paletas modernas y valientes, p. ej.: violeta #8B5CF6 + fucsia #EC4899 sobre #0B1220; azul #2563EB + cian #06B6D4 sobre #F8FAFC; esmeralda #10B981 + lima #84CC16; naranja #F97316 + rosa #F43F5E. Texto SIEMPRE legible sobre su fondo.
- Riqueza: 10-18 elementos como mínimo (fondo decorado + jerarquía de textos + tarjetas/chips/acentos + una línea o flecha de acento si aporta). Un título solo NO es un diseño.
- Remata con detalles finos: una cinta/etiqueta pequeña, puntos decorativos, o un pie con datos — lo que haga ver la pieza terminada y profesional.

COMPOSICIÓN DE DATOS (cuando el pedido lo amerite — informes, dashboards, avisos con cifras):
- Gráfica de barras: varios "rect" verticales con ALTURA proporcional a cada valor (todos apoyados en la misma línea base), colores de una paleta, + un "text" de valor arriba de cada barra y un "text" de etiqueta abajo. Agrega título y, si aplica, una "line" como eje.
- Gráfica de dona/anillo: usa el tipo "ring" grande + un "text" central con el porcentaje/KPI.
- Tabla: dibuja la cuadrícula con "line" (horizontales y verticales) y un "rect" de color como fila de encabezado; pon un "text" por celda, alineado. Filas de alto uniforme.
- Tarjetas KPI / infografía: "rect" con rx y shadow como tarjeta, un número GRANDE (text fs 48-96 bold) + etiqueta pequeña; combina con un icono hecho de formas o una "foto".
- Línea de tiempo / pasos: "ellipse"/"star" numeradas conectadas por "line", con textos cortos.

FOTOS EN EL DISEÑO:
- Para retratos, productos o logos circulares usa "foto" con "clip":"ellipse". Un "rect" con shadow detrás como marco luce premium.

SÉ ESPECÍFICO AL PEDIDO (nada genérico):
- Usa LITERALMENTE los textos, nombres, cifras, fechas y tema que dio el usuario. Prohibido el contenido de relleno vago ("Título aquí", "Lorem", frases genéricas que no hablan de SU pedido).
- Si el pedido menciona una industria o contexto (transporte, taller, comida, oficina…), TODO debe reflejarlo: paleta, fotos, iconografía y redacción de los textos.
- Si falta un dato que la pieza necesita (teléfono, dirección, precio), pon un marcador OBVIO tipo "TU TELÉFONO AQUÍ" — nunca inventes datos realistas.
- Piensa qué pieza necesita el usuario (póster, tarjeta, portada, anuncio, aviso interno) y dimensiona el artboard y la jerarquía para ESE uso.

Responde ÚNICAMENTE con el JSON."""

_BLEND = {"normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge",
          "color-burn", "hard-light", "soft-light", "difference", "exclusion", "hue",
          "saturation", "color", "luminosity"}
# Formas válidas para la máscara de recorte (clipping mask) de una imagen/foto.
_CLIP_OK = {"rect", "ellipse", "triangle", "diamond", "star", "hexagon"}


def validar_canvas(raw: dict, contener: bool = False) -> dict:
    els = []
    for e in _lst(raw.get("elementos"))[:200]:
        if not isinstance(e, dict):
            continue
        tipo = str(e.get("tipo") or e.get("type") or "").strip()
        if tipo not in CANVAS_TIPOS:
            continue
        if tipo == "foto":
            # FOTO real: el frontend la genera con el motor de imágenes (Gemini)
            # y la inserta en el hueco que el diseño reservó.
            fprompt = str(e.get("prompt") or "").strip()[:600]
            if not fprompt:
                continue
            foto_el = {
                "tipo": "foto", "prompt": fprompt,
                "x": round(_clamp(_num(e.get("x")), -2000, 6000), 1),
                "y": round(_clamp(_num(e.get("y")), -2000, 6000), 1),
                "w": round(_clamp(_num(e.get("w"), 480), 40, 4000), 1),
                "h": round(_clamp(_num(e.get("h"), 360), 40, 4000), 1),
            }
            clv = str(e.get("clip") or "").strip().lower()
            if clv in _CLIP_OK:
                foto_el["clip"] = clv
            els.append(foto_el)
            continue
        es_texto = tipo in ("text", "sticky")
        el = {
            "tipo": tipo,
            "x": round(_clamp(_num(e.get("x")), -2000, 6000), 1),
            "y": round(_clamp(_num(e.get("y")), -2000, 6000), 1),
            "w": round(_clamp(_num(e.get("w"), 120), 4, 6000), 1),
            "h": round(_clamp(_num(e.get("h"), 120), 4, 6000), 1),
            "stroke": _color(e.get("stroke"), "#1E293B"),
            "fill": _color(e.get("fill"), "none" if tipo == "text" else "#93C5FD"),
            "sw": round(_clamp(_num(e.get("sw"), 0 if es_texto else 3), 0, 24), 1),
        }
        # Texto
        if es_texto:
            el["text"] = str(e.get("text") or "").strip()[:600]
            el["fs"] = round(_clamp(_num(e.get("fs"), 24), 8, 240), 0)
            for f in ("bold", "italic"):
                if e.get(f):
                    el[f] = True
            al = str(e.get("talign") or "").strip()
            if al in ("l", "c", "r"):
                el["talign"] = al
            fo = str(e.get("font") or "").strip()
            if fo in ("sans", "serif", "mono", "hand"):
                el["font"] = fo
            for f in ("underline", "strike"):
                if e.get(f):
                    el[f] = True
            hl = _color(e.get("highlight"), None)
            if hl and hl != "none" and tipo == "text":
                el["highlight"] = hl
        if tipo == "frame":
            el["text"] = str(e.get("text") or "Mesa").strip()[:60]
        # Líneas / flechas
        if tipo in ("line", "arrow"):
            pts_raw = e.get("points") or []
            pts = []
            if isinstance(pts_raw, list):
                for p in pts_raw[:100]:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        pts.append([round(_num(p[0]), 1), round(_num(p[1]), 1)])
            if len(pts) < 2:
                continue  # sin puntos válidos → se descarta
            el["points"] = pts
        # Estilo opcional
        for f, lo, hi in (("op", 0.1, 1), ("fillOp", 0.1, 1)):
            if e.get(f) is not None:
                el[f] = round(_clamp(_num(e.get(f), 1), lo, hi), 2)
        if e.get("rx") is not None:
            el["rx"] = round(_clamp(_num(e.get("rx"), 10), 0, 400), 1)
        if e.get("rot") is not None:
            el["rot"] = round(_clamp(_num(e.get("rot"), 0), -360, 360), 1)
        g = _color(e.get("grad"), None)
        if g and g != "none":
            el["grad"] = g
            if e.get("gradAngle") is not None:
                el["gradAngle"] = round(_clamp(_num(e.get("gradAngle"), 135), 0, 360), 0)
            gtp = str(e.get("gradType") or "").strip().lower()
            if gtp == "radial":
                el["gradType"] = "radial"
        if e.get("shadow"):
            el["shadow"] = True
        d = str(e.get("dash") or "").strip()
        if d in ("solid", "dashed", "dotted"):
            el["dash"] = d
        b = str(e.get("blend") or "").strip()
        if b in _BLEND:
            el["blend"] = b
        els.append(el)

    out = {"elementos": els}
    fondo = _color(raw.get("fondo"), None)
    if fondo and fondo != "none":
        out["fondo"] = fondo
    ab = raw.get("artboard") or {}
    if isinstance(ab, dict) and ab.get("w") and ab.get("h"):
        out["artboard"] = {"w": round(_clamp(_num(ab.get("w"), 1080), 40, 8000), 0),
                           "h": round(_clamp(_num(ab.get("h"), 1080), 40, 8000), 0)}
    # Contención (solo diseños completos): el lienzo NO recorta como Canva, así
    # que un adorno que "sangra" fuera del póster queda flotando suelto. Todo
    # elemento se mete al área de diseño (se encoge/mueve lo justo).
    if contener:
        bw = float((out.get("artboard") or {}).get("w") or 1080)
        bh = float((out.get("artboard") or {}).get("h") or 1080)
        for el in els:
            el["w"] = min(el["w"], bw)
            el["h"] = min(el["h"], bh)
            el["x"] = round(_clamp(el["x"], 0, bw - el["w"]), 1)
            el["y"] = round(_clamp(el["y"], 0, bh - el["h"]), 1)
    return out


def generar_canvas(pedido: str, cfg: dict, imagenes=None, contexto: str = "",
                   gemini_key: str = "") -> dict:
    user = f"Pedido del cliente:\n{pedido.strip()}"
    if contexto:
        user += ("\n\nDATOS REALES para incorporar al diseño (úsalos textualmente donde "
                 f"correspondan: nombres, números, fechas):\n{contexto[:4000]}")
    if imagenes:
        user += ("\n\nEl cliente adjuntó FOTOS de referencia (un boceto, una imagen, "
                 "una captura). Úsalas como base del diseño.")
    texto = llamar_ia_texto(cfg, gemini_key, SYSTEM_PROMPT_CANVAS, user,
                            imagenes=imagenes, temperature=0.6, max_tokens=7000)
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió un diseño válido. Reformula tu pedido.")
    plan = validar_canvas(raw, contener=True)
    if not plan["elementos"]:
        raise _PlanError("La IA no propuso elementos. Sé más específico (p. ej. 'un póster de seguridad industrial').")
    return plan


# ── Edición conversacional del Canvas ("Chat mágico") ─────────────────────────
# La IA recibe los elementos ACTUALES + una instrucción (o una imagen del lienzo)
# y devuelve OPERACIONES (update/add/delete/fondo). Preserva la identidad de los
# elementos (edita por id) en vez de recrear todo el diseño.

# Props que la IA puede tocar en "update"/"add". Todo lo demás se ignora.
def _validar_cambios(d) -> dict:
    if not isinstance(d, dict):
        return {}
    out: dict = {}
    for k in ("x", "y"):
        if d.get(k) is not None:
            out[k] = round(_clamp(_num(d[k]), -2000, 6000), 1)
    for k in ("w", "h"):
        if d.get(k) is not None:
            out[k] = round(_clamp(_num(d[k]), 4, 6000), 1)
    if d.get("sw") is not None:
        out["sw"] = round(_clamp(_num(d["sw"]), 0, 24), 1)
    if d.get("fs") is not None:
        out["fs"] = round(_clamp(_num(d["fs"]), 8, 240), 0)
    for k in ("fill", "stroke", "grad"):
        if d.get(k) is not None:
            c = _color(d[k], None)
            if c is not None:
                out[k] = c
    for k in ("bold", "italic", "shadow"):
        if d.get(k) is not None:
            out[k] = bool(d[k])
    for k in ("op", "fillOp"):
        if d.get(k) is not None:
            out[k] = round(_clamp(_num(d[k], 1), 0.1, 1), 2)
    if d.get("rx") is not None:
        out["rx"] = round(_clamp(_num(d["rx"]), 0, 400), 1)
    if d.get("rot") is not None:
        out["rot"] = round(_clamp(_num(d["rot"]), -360, 360), 1)
    al = str(d.get("talign") or "").strip()
    if al in ("l", "c", "r"):
        out["talign"] = al
    fo = str(d.get("font") or "").strip()
    if fo in ("sans", "serif", "mono", "hand"):
        out["font"] = fo
    da = str(d.get("dash") or "").strip()
    if da in ("solid", "dashed", "dotted"):
        out["dash"] = da
    b = str(d.get("blend") or "").strip()
    if b in _BLEND:
        out["blend"] = b
    if "clip" in d:  # máscara de recorte de una imagen ("" = quitarla)
        cl = str(d.get("clip") or "").strip().lower()
        out["clip"] = cl if cl in _CLIP_OK else ""
    if d.get("gradAngle") is not None:
        out["gradAngle"] = round(_clamp(_num(d.get("gradAngle"), 135), 0, 360), 0)
    gt = str(d.get("gradType") or "").strip().lower()
    if gt in ("linear", "radial"):
        out["gradType"] = gt
    for k in ("underline", "strike"):
        if d.get(k) is not None:
            out[k] = bool(d[k])
    if "highlight" in d:  # resaltado del texto ("" = quitar)
        hl = _color(d.get("highlight"), None)
        out["highlight"] = hl if (hl and hl != "none") else ""
    if d.get("text") is not None:
        out["text"] = str(d["text"])[:600]
    return out


def _resumen_elementos(elementos) -> list:
    """Compacta los elementos actuales para el prompt (id, tipo, geometría, props clave).
    Cap agresivo: menos tokens = respuesta MUCHO más rápida (evita timeouts ASGI)."""
    out = []
    for e in _lst(elementos)[:80]:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("id") or "").strip()
        tipo = str(e.get("type") or e.get("tipo") or "").strip()
        if not eid or not tipo:
            continue
        r = {
            "id": eid, "tipo": tipo,
            "x": round(_num(e.get("x")), 0), "y": round(_num(e.get("y")), 0),
            "w": round(_num(e.get("w")), 0), "h": round(_num(e.get("h")), 0),
        }
        if e.get("text"):
            r["text"] = str(e.get("text"))[:50]
        for k in ("fill", "stroke", "fs"):
            if e.get(k) not in (None, ""):
                r[k] = e.get(k)
        out.append(r)
    return out


def validar_ops(raw: dict, ids: set) -> list:
    ops = []
    for o in _lst(raw.get("ops"))[:200]:
        if not isinstance(o, dict):
            continue
        kind = str(o.get("op") or "").strip()
        if kind == "update":
            oid = str(o.get("id") or "").strip()
            if oid not in ids:
                continue
            cambios = _validar_cambios(o.get("cambios") or {})
            if cambios:
                ops.append({"op": "update", "id": oid, "cambios": cambios})
        elif kind == "add":
            elemento = o.get("elemento") or {}
            if str((elemento if isinstance(elemento, dict) else {}).get("tipo") or "").strip() == "foto":
                continue  # en el chat las fotos van SIEMPRE por "add_foto"
            elv = validar_canvas({"elementos": [elemento]})["elementos"]
            if elv:
                ops.append({"op": "add", "elemento": elv[0]})
        elif kind == "add_foto":
            # Foto real: el prompt se manda al generador de imágenes (Gemini) y
            # el frontend inserta el resultado en la posición que decidió la IA.
            fprompt = str(o.get("prompt") or "").strip()[:600]
            if fprompt:
                foto = {
                    "op": "add_foto", "prompt": fprompt,
                    "x": round(_clamp(_num(o.get("x"), 120), -2000, 6000), 1),
                    "y": round(_clamp(_num(o.get("y"), 120), -2000, 6000), 1),
                    "w": round(_clamp(_num(o.get("w"), 480), 40, 4000), 1),
                    "h": round(_clamp(_num(o.get("h"), 360), 40, 4000), 1),
                }
                cl = str(o.get("clip") or "").strip().lower()
                if cl in _CLIP_OK:
                    foto["clip"] = cl  # foto recortada a una forma (círculo, etc.)
                ops.append(foto)
        elif kind == "align":
            # Alinea 2+ elementos existentes entre sí.
            aids = [str(i) for i in _lst(o.get("ids")) if str(i) in ids]
            modo = str(o.get("modo") or "").strip()
            if len(aids) >= 2 and modo in ("left", "cx", "right", "top", "cy", "bottom"):
                ops.append({"op": "align", "ids": aids, "modo": modo})
        elif kind == "distribute":
            aids = [str(i) for i in _lst(o.get("ids")) if str(i) in ids]
            eje = str(o.get("eje") or "").strip()
            if len(aids) >= 3 and eje in ("h", "v"):
                ops.append({"op": "distribute", "ids": aids, "eje": eje})
        elif kind == "reorder":
            oid = str(o.get("id") or "").strip()
            a = str(o.get("a") or "").strip()
            if oid in ids and a in ("front", "back"):
                ops.append({"op": "reorder", "id": oid, "a": a})
        elif kind == "duplicate":
            oid = str(o.get("id") or "").strip()
            if oid in ids:
                ops.append({"op": "duplicate", "id": oid,
                            "dx": round(_clamp(_num(o.get("dx"), 24), -6000, 6000), 1),
                            "dy": round(_clamp(_num(o.get("dy"), 24), -6000, 6000), 1)})
        elif kind == "tile":
            tids = [str(i) for i in _lst(o.get("ids")) if str(i) in ids]
            if tids:
                ops.append({"op": "tile", "ids": tids,
                            "cols": int(_clamp(_num(o.get("cols"), 2), 1, 20)),
                            "rows": int(_clamp(_num(o.get("rows"), 2), 1, 20)),
                            "gapX": round(_clamp(_num(o.get("gapX"), 20), 0, 2000), 1),
                            "gapY": round(_clamp(_num(o.get("gapY"), 20), 0, 2000), 1)})
        elif kind == "delete":
            oid = str(o.get("id") or "").strip()
            if oid in ids:
                ops.append({"op": "delete", "id": oid})
        elif kind == "fondo":
            c = _color(o.get("color"), None)
            if c and c != "none":
                ops.append({"op": "fondo", "color": c})
    return ops


SYSTEM_PROMPT_EDITAR = """Eres un asistente que EDITA un lienzo de diseño (estilo Figma/Canva) según la instrucción del usuario, en español.

Recibes la lista de elementos ACTUALES (JSON, cada uno con su "id", "tipo", posición y props) y una instrucción (y a veces una imagen del lienzo). Tu única salida es un objeto JSON con este esquema EXACTO (sin markdown, sin texto extra):
{
  "ops": [
    { "op": "update", "id": "<id existente>", "cambios": { <solo las props a cambiar> } },
    { "op": "add", "elemento": { "tipo": "<tipo>", "x": <n>, "y": <n>, "w": <n>, "h": <n>, ... } },
    { "op": "add_foto", "prompt": "<descripción DETALLADA de la foto>", "x": <n>, "y": <n>, "w": <n>, "h": <n>, "clip": "<forma opcional>" },
    { "op": "align", "ids": ["<id>", "<id>", ...], "modo": "left|cx|right|top|cy|bottom" },
    { "op": "distribute", "ids": ["<id>", "<id>", "<id>", ...], "eje": "h|v" },
    { "op": "reorder", "id": "<id>", "a": "front|back" },
    { "op": "duplicate", "id": "<id>", "dx": <n>, "dy": <n> },
    { "op": "tile", "ids": ["<id>", ...], "cols": <n>, "rows": <n>, "gapX": <n>, "gapY": <n> },
    { "op": "delete", "id": "<id existente>" },
    { "op": "fondo", "color": "#RRGGBB" }
  ]
}

Props editables (en "cambios" y "elemento"): x, y, w, h, fill, stroke, sw, rx, rot, op, fillOp, grad, shadow, dash, blend. En textos (tipo text/sticky) además: text, fs (14-140), bold, italic, talign (l|c|r), font (sans|serif|mono|hand).
Tipos válidos para "add": rect, ellipse, diamond, triangle, star, hexagon, speech, chevron, parallelogram, cloud, semicircle, ring, line, arrow, text, sticky, frame.

Reglas:
- Cambia SOLO lo que pide la instrucción. Usa "update" sobre los ids EXISTENTES (no recrees el diseño entero).
- "más grande/agranda" → sube w,h (y fs en textos). "mueve" → cambia x,y. "recolorea/cambia color" → fill o stroke. "más transparente" → op.
- Si agregas un elemento, ponlo con coordenadas coherentes dentro del lienzo y con buen contraste.
- Para poner texto usa fill:"none", stroke = color del texto, sw:0.
- Colores en hex #RRGGBB. Devuelve solo los cambios necesarios (pocas ops, precisas).

HERRAMIENTAS DE LAYOUT (úsalas para trabajo PROFESIONAL, no muevas todo a mano con "update"):
- "align": alinea 2+ elementos entre sí (izquierda/centro-horizontal/derecha/arriba/centro-vertical/abajo). Ej.: "alinea todo al centro" → align con modo "cx". Ideal para ordenar botones, tarjetas o una columna de textos.
- "distribute": reparte 3+ elementos con espaciado uniforme (eje "h" u "v"). Ej.: "reparte parejo los 3 iconos".
- "reorder": manda un elemento al frente ("front") o al fondo ("back"). Ej.: "trae el título al frente", "manda la foto atrás".
- "duplicate": clona un elemento desplazado (dx,dy). Útil para repetir tarjetas/filas.
- "tile": repite la selección en una malla cols×rows con separación gapX/gapY. Ej.: "repite esta etiqueta en una hoja de 3 por 4 para imprimir".
- Estilo fino en update.cambios: gradAngle (0-360, ángulo del degradado) y gradType ("radial"); en textos underline/strike (bool) y highlight (#RRGGBB para resaltar el fondo del texto, "" para quitar). Ej.: "resalta el título en amarillo" → update {"highlight":"#FEF08A"}.
- "clip" (en add_foto y en update de una imagen): recorta la imagen a una forma: rect, ellipse, triangle, diamond, star, hexagon (usa "ellipse" para círculo/óvalo). Ej.: "pon la foto en un círculo" → add_foto con "clip":"ellipse", o update {"clip":"ellipse"} sobre la imagen. Para quitar la máscara: update {"clip":""}.

FOTOS REALES ("add_foto") — MUY IMPORTANTE:
- REGLA DE ORO: si el usuario pide agregar CUALQUIER objeto/escena del mundo real (un camión, una persona, una oficina, un producto, comida, un paisaje, maquinaria…), usa "add_foto" POR DEFECTO — aunque no diga la palabra "foto". NUNCA imites objetos reales con rectángulos/círculos: eso se ve amateur.
- Usa figuras geométricas SOLO si el usuario pide explícitamente un "dibujo", "figura", "forma", "icono" o "ilustración con formas", o si es un elemento gráfico de diseño (botón, marco, cinta, línea decorativa).
- En "prompt" describe la foto con DETALLE en español (sujeto, estilo fotográfico, iluminación, encuadre, fondo) — ese texto va directo al generador de imágenes. Ej.: "camión tractocamión de quinta rueda blanco, fotografía profesional lateral, luz de día, fondo de patio logístico difuminado".
- Elige x,y,w,h coherentes con la composición actual (dónde encaja mejor la foto, tamaño proporcionado, sin tapar textos).
- Máximo 2 "add_foto" por instrucción. Puedes combinarla con otras ops (p. ej. un marco "rect" con shadow detrás de la foto).

Responde ÚNICAMENTE con el JSON."""


def editar_canvas(instruccion: str, elementos, cfg: dict, imagenes=None, contexto: str = "",
                  gemini_key: str = "") -> dict:
    resumen = _resumen_elementos(elementos)
    ids = {e["id"] for e in resumen}
    user = (f"Elementos actuales (JSON):\n{json.dumps(resumen, ensure_ascii=False)}\n\n"
            f"Instrucción del usuario:\n{instruccion.strip()}")
    if contexto:
        user += f"\n\nDatos de contexto para usar (nombres, números, fechas reales):\n{contexto[:4000]}"
    if imagenes:
        user += ("\n\nAdjunto una IMAGEN del lienzo actual renderizado; úsala para entender el "
                 "diseño, detectar problemas (alineación, contraste, jerarquía) y proponer mejoras.")
    texto = llamar_ia_texto(cfg, gemini_key, SYSTEM_PROMPT_EDITAR, user,
                            imagenes=imagenes, temperature=0.3, max_tokens=6000)
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió cambios válidos. Reformula tu instrucción.")
    ops = validar_ops(raw, ids)
    if not ops:
        raise _PlanError("La IA no propuso cambios aplicables. Sé más específico (p. ej. 'agranda el título y ponlo azul').")
    return {"ops": ops}


# ══════════════════════════════ CHECKLISTS ══════════════════════════════════
# Asistente del constructor de checklists (flujos de mantenimiento): a partir de
# la descripción, genera el formulario completo (nombre, descripción y CAMPOS con
# tipos, secciones, obligatorios, opciones, rangos, condiciones y evidencia
# fotográfica). El plan lo dibuja el builder del frontend; el usuario lo revisa
# y lo guarda. Aislado: solo conoce el esquema de campos del builder.
TIPOS_CAMPO_CHECKLIST = {
    "texto", "parrafo", "numero", "booleano", "seleccion", "foto", "galeria",
    "fecha", "unidad", "km_unidad", "termo", "horas_termo",
}

SYSTEM_CHECKLIST = """Eres un experto en operaciones de transporte/logística mexicanas y en diseño de formularios de campo (checklists) que se llenan desde un CELULAR.
A partir del pedido del usuario, diseñas el checklist completo: claro, rápido de llenar con una mano y con evidencia fotográfica donde importa.

Tu ÚNICA salida es un objeto JSON con este esquema EXACTO (sin texto adicional, sin markdown):
{
  "nombre": "<nombre corto del checklist>",
  "descripcion": "<1-2 frases: para qué sirve y cuándo se llena>",
  "campos": [
    {
      "seccion": "<grupo, ej. 'Documentación', 'Motor', 'Llantas', 'General'>",
      "etiqueta": "<pregunta corta y clara>",
      "tipo": "texto|parrafo|numero|booleano|seleccion|foto|galeria|fecha|unidad|km_unidad|termo|horas_termo",
      "obligatorio": true,
      "ayuda": "<aclaración breve o ''>",
      "opciones": ["solo si tipo=seleccion, 2-6 opciones cortas"],
      "min_valor": null,
      "max_valor": null,
      "depende_de_indice": null,
      "mostrar_si": "",
      "foto_aplica": "",
      "foto_obligatoria": false
    }
  ],
  "resumen": "<1 frase en español de lo que armaste>"
}

Tipos disponibles:
- "booleano" = Sí/No — el rey de las inspecciones; úsalo para puntos de revisión.
- "seleccion" = lista de opciones (estado: Bueno/Regular/Malo…).
- "numero" = medida/cantidad; usa min_valor/max_valor si hay rango razonable (ej. presión, nivel).
- "texto" corto · "parrafo" largo (observaciones) · "fecha" · "foto" (una) · "galeria" (varias fotos).
- "unidad" = seleccionar el camión/unidad de la flota. "km_unidad" = kilometraje (actualiza el catálogo de flota).
- "termo" = caja refrigerada · "horas_termo" = horas del termo (actualiza catálogo).

Reglas de oro:
- Agrupa con "seccion" (3-8 campos por sección, en orden lógico de recorrido físico).
- Si es una inspección de unidad/vehículo: el PRIMER campo es tipo "unidad" (obligatorio) y el segundo "km_unidad" (obligatorio). Si mencionan refrigeración/termo, incluye "termo" y "horas_termo".
- En puntos críticos Sí/No pide EVIDENCIA cuando algo está mal: "foto_aplica": "si_no" y "foto_obligatoria": true. Usa "si_si" si la evidencia aplica cuando responden Sí. "siempre" para foto fija.
- "depende_de_indice": índice (base 0) de un campo ANTERIOR de tipo booleano o seleccion; "mostrar_si" = "si"/"no" (booleano) o la opción exacta (seleccion). Úsalo p. ej. para pedir detalle cuando algo falla. Si no aplica: null y "".
- Cierra con una sección "General" u "Observaciones": un "parrafo" opcional y una "galeria" de evidencias.
- 10-25 campos salvo que pidan otra cosa. Español de México, directo y profesional.

Responde ÚNICAMENTE con el JSON."""


def _validar_checklist_ia(raw: dict) -> dict:
    """Normaliza el plan del checklist: tipos válidos, opciones, rangos,
    dependencias por índice y evidencia fotográfica coherente."""
    campos = []
    for c in _lst(raw.get("campos"))[:60]:
        if not isinstance(c, dict):
            continue
        etiqueta = str(c.get("etiqueta") or "").strip()[:200]
        tipo = str(c.get("tipo") or "texto").strip().lower()
        if not etiqueta or tipo not in TIPOS_CAMPO_CHECKLIST:
            continue
        opciones = [str(o).strip()[:120] for o in _lst(c.get("opciones")) if str(o).strip()][:10]
        if tipo == "seleccion" and len(opciones) < 2:
            tipo = "texto"  # selección sin opciones no sirve → texto
        dep = c.get("depende_de_indice")
        try:
            dep = int(dep) if dep is not None else None
        except (TypeError, ValueError):
            dep = None
        foto_aplica = str(c.get("foto_aplica") or "").strip().lower()
        if foto_aplica not in ("", "siempre", "si_si", "si_no"):
            foto_aplica = ""
        if tipo == "booleano":
            pass  # todos los foto_aplica son válidos
        elif foto_aplica in ("si_si", "si_no"):
            foto_aplica = "siempre"  # condicionales de Sí/No solo aplican a booleanos
        if tipo in ("foto", "galeria"):
            foto_aplica = ""  # el campo YA es una foto
        campo = {
            "seccion": str(c.get("seccion") or "").strip()[:120],
            "etiqueta": etiqueta,
            "tipo": tipo,
            "obligatorio": bool(c.get("obligatorio")),
            "ayuda": str(c.get("ayuda") or "").strip()[:300],
            "opciones": opciones if tipo == "seleccion" else [],
            "min_valor": (_num(c.get("min_valor"), None) if tipo == "numero" and c.get("min_valor") is not None else None),
            "max_valor": (_num(c.get("max_valor"), None) if tipo == "numero" and c.get("max_valor") is not None else None),
            "depende_de_indice": dep,
            "mostrar_si": str(c.get("mostrar_si") or "").strip()[:120],
            "foto_aplica": foto_aplica,
            "foto_obligatoria": bool(c.get("foto_obligatoria")) and bool(foto_aplica),
        }
        campos.append(campo)
    # Segunda pasada: valida dependencias (solo hacia un campo ANTERIOR de
    # tipo booleano/seleccion, con un mostrar_si coherente).
    for i, campo in enumerate(campos):
        dep = campo["depende_de_indice"]
        ok = (
            dep is not None and 0 <= dep < i
            and campos[dep]["tipo"] in ("booleano", "seleccion")
            and campo["mostrar_si"]
        )
        if ok and campos[dep]["tipo"] == "booleano":
            ok = campo["mostrar_si"].lower() in ("si", "no")
            campo["mostrar_si"] = campo["mostrar_si"].lower()
        if ok and campos[dep]["tipo"] == "seleccion":
            ok = campo["mostrar_si"] in campos[dep]["opciones"]
        if not ok:
            campo["depende_de_indice"] = None
            campo["mostrar_si"] = ""
    return {
        "nombre": str(raw.get("nombre") or "").strip()[:160],
        "descripcion": str(raw.get("descripcion") or "").strip()[:600],
        "campos": campos,
        "resumen": str(raw.get("resumen") or "").strip()[:400],
    }


def generar_checklist(pedido: str, cfg: dict, imagenes=None, contexto: str = "",
                      gemini_key: str = "") -> dict:
    """Genera el plan de un checklist (formulario) para el builder del frontend."""
    user = f"Pedido del usuario:\n{pedido.strip()}"
    if contexto and contexto.strip():
        user += f"\n\nContexto (campos que YA existen u otras notas):\n{contexto.strip()[:2000]}"
    if imagenes:
        user += ("\n\nEl usuario adjuntó FOTOS de referencia (un formato en papel, "
                 "una hoja de inspección existente). Convierte lo que veas en campos.")
    texto = llamar_ia_texto(cfg, gemini_key, SYSTEM_CHECKLIST, user,
                            imagenes=imagenes, temperature=0.4, max_tokens=7000)
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió un checklist válido. Reformula tu pedido.")
    plan = _validar_checklist_ia(raw)
    if not plan["campos"]:
        raise _PlanError("La IA no propuso campos. Sé más específico "
                         "(p. ej. 'inspección diaria de tractocamión con llantas, luces y niveles').")
    return plan


# ══════════════ Analista del Simulador de Viajes (recomendaciones) ══════════════
SYSTEM_ANALISIS_VIAJE = """Eres un analista senior de logística de transporte de carga en México. Recibes el resumen de una SIMULACIÓN de viaje (ruta, unidad, costos, utilidad) y produces observaciones ACCIONABLES para el tomador de decisiones.

Tu única salida es un objeto JSON (sin markdown, sin texto extra):
{
  "observaciones": [ { "nivel": "ok|info|alerta|critico", "texto": "<observación concreta en español, 1 frase, con números>" } ],
  "veredicto": "<1 frase: ¿conviene tomar el viaje y bajo qué condición?>"
}

Reglas:
- 4 a 8 observaciones, ordenadas de lo más importante a lo menos.
- Usa los NÚMEROS del resumen (porcentajes, pesos, litros); nada genérico.
- Cubre cuando aplique: margen vs. riesgo, peso del diésel/casetas/termo en el costo, tiempos muertos en paradas, rendimiento capturado vs. típico del tipo de unidad, restricciones de circulación, y si conviene otra unidad o negociar el precio.
- Español de México, directo y profesional. Sin emojis.

Responde ÚNICAMENTE con el JSON."""

_NIVELES_OBS = {"ok", "info", "alerta", "critico"}


def _validar_analisis_viaje(raw: dict) -> dict:
    obs = []
    for o in (raw.get("observaciones") if isinstance(raw.get("observaciones"), list) else [])[:12]:
        if not isinstance(o, dict):
            continue
        txt = str(o.get("texto") or "").strip()[:280]
        if not txt:
            continue
        nivel = str(o.get("nivel") or "info").strip().lower()
        obs.append({"nivel": nivel if nivel in _NIVELES_OBS else "info", "texto": txt})
    return {"observaciones": obs, "veredicto": str(raw.get("veredicto") or "").strip()[:300]}


def _cfg_solo_claude(cfg: dict) -> dict:
    """El Simulador de Viajes usa EXCLUSIVAMENTE Claude (Anthropic).
    Ignora Gemini y DeepSeek: si la empresa tiene Anthropic configurado usa esa
    llave; si no, cae a la llave compartida ANTHROPIC_API_KEY del backend."""
    import os
    if cfg.get("proveedor") == "anthropic" and (cfg.get("api_key") or "").strip():
        return {**cfg, "proveedor": "anthropic"}
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise _PlanError("El Simulador usa Claude (Anthropic). Pide al administrador que "
                         "configure ANTHROPIC_API_KEY en el .env del backend para activar el asistente.")
    return {"proveedor": "anthropic", "api_key": key, "base_url": "", "modelo": ""}


def generar_analisis_viaje(pedido: str, cfg: dict, imagenes=None, contexto: str = "",
                           gemini_key: str = "") -> dict:
    """Analiza el resumen de una simulación de viaje y devuelve observaciones (Claude)."""
    cfg = _cfg_solo_claude(cfg)
    user = f"Resumen de la simulación (JSON):\n{pedido.strip()[:6000]}"
    if contexto and contexto.strip():
        user += f"\n\nContexto adicional:\n{contexto.strip()[:1500]}"
    texto = llamar_ia_texto(cfg, "", SYSTEM_ANALISIS_VIAJE, user,
                            imagenes=imagenes, temperature=0.4, max_tokens=2500)
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió un análisis válido. Intenta de nuevo.")
    plan = _validar_analisis_viaje(raw)
    if not plan["observaciones"]:
        raise _PlanError("La IA no produjo observaciones. Intenta de nuevo.")
    return plan


SYSTEM_CHAT_VIAJE = """Eres un analista experto en costos y operación de autotransporte de carga en México, integrado como asistente conversacional dentro de un Simulador de Viajes. El usuario te hace preguntas o comentarios sobre EL VIAJE que está simulando.

Reglas:
- Apóyate en los datos del viaje (JSON) y en la conversación previa que se te entregan. Si un dato falta, dilo y sugiere qué capturar en el simulador.
- Español de México, claro, directo y profesional. Sin emojis.
- Respuestas breves y accionables; usa viñetas cuando ayude. Si te piden un cálculo, hazlo con los datos dados y muestra el razonamiento en 1-2 líneas.
- Los precios por caseta son ESTIMADOS (no hay API pública de tarifas); acláralo si es relevante y no inventes montos exactos por caseta.
- No repitas todo el resumen: responde la pregunta concreta."""


def chat_viaje(pedido: str, cfg: dict, imagenes=None, contexto: str = "",
               gemini_key: str = "") -> dict:
    """Chat conversacional del Simulador (Claude): responde preguntas del usuario
    sobre el viaje simulado. Devuelve texto libre en {'respuesta': ...}."""
    cfg = _cfg_solo_claude(cfg)
    user = ""
    if contexto and contexto.strip():
        user += f"Datos del viaje simulado y conversación previa:\n{contexto.strip()[:6500]}\n\n"
    user += f"Mensaje del usuario:\n{pedido.strip()[:2000]}"
    texto = llamar_ia_texto(cfg, "", SYSTEM_CHAT_VIAJE, user,
                            imagenes=imagenes, temperature=0.5, max_tokens=1200)
    respuesta = (texto or "").strip()
    if not respuesta:
        raise _PlanError("La IA no devolvió respuesta. Intenta de nuevo.")
    return {"respuesta": respuesta[:4000]}


# ══════════════════ Guionista de VIDEO (títulos en pantalla) ══════════════════
SYSTEM_GUION_VIDEO = """Eres un guionista de video para una empresa mexicana de transporte/logística. A partir de la descripción del cliente, escribes los TÍTULOS/textos que aparecen en pantalla (on-screen), con sus tiempos, para un editor de video.

Tu única salida es un objeto JSON (sin markdown, sin texto extra):
{
  "titulos": [ { "text": "<texto corto en pantalla>", "start": <segundos>, "dur": <segundos>, "posV": "top|center|bottom", "fontSize": <28-96> } ],
  "resumen": "<1 frase de lo que armaste>"
}

Reglas:
- Textos CORTOS y contundentes (máx ~8 palabras por título; usa \\n para partir en 2 líneas si hace falta).
- Ordena por "start" ascendente y NO los encimes: cada título termina (start+dur) antes de que empiece el siguiente, o déjalos claramente separados.
- Estructura típica: 1 título de ENTRADA (start ~0.3, posV "center", fontSize grande ~84), 3-6 mensajes clave (posV "bottom", ~52), y 1 CIERRE.
- Español de México, claro y profesional. Sin emojis salvo que sumen.
- Entre 3 y 10 títulos, según lo que pida el cliente. Duraciones realistas (2.5-4 s por mensaje).

Responde ÚNICAMENTE con el JSON."""


def _validar_guion_video(raw: dict) -> dict:
    """Filtra/normaliza los títulos del guion para el editor de video."""
    titulos = []
    _t = raw.get("titulos")
    for t in (_t if isinstance(_t, list) else [])[:40]:
        if not isinstance(t, dict):
            continue
        txt = str(t.get("text") or "").strip()[:180]
        if not txt:
            continue
        pos = str(t.get("posV") or "bottom").strip().lower()
        if pos not in ("top", "center", "bottom"):
            pos = "bottom"
        titulos.append({
            "text": txt,
            "start": round(_clamp(_num(t.get("start")), 0, 36000), 2),
            "dur": round(_clamp(_num(t.get("dur"), 3) or 3, 0.5, 60), 2),
            "posV": pos,
            "fontSize": int(_clamp(_num(t.get("fontSize"), 56) or 56, 20, 120)),
        })
    titulos.sort(key=lambda x: x["start"])
    return {"titulos": titulos, "resumen": str(raw.get("resumen") or "").strip()[:300]}


def generar_guion_video(pedido: str, cfg: dict, imagenes=None, contexto: str = "",
                        gemini_key: str = "") -> dict:
    """Genera los títulos en pantalla (con tiempos) de un video a partir de su descripción."""
    user = f"Descripción del video (de qué trata):\n{pedido.strip()}"
    if contexto and contexto.strip():
        user += f"\n\nContexto (medios/clips que ya hay, duración, etc.):\n{contexto.strip()[:1500]}"
    texto = llamar_ia_texto(cfg, gemini_key, SYSTEM_GUION_VIDEO, user,
                            imagenes=imagenes, temperature=0.6, max_tokens=3000)
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió títulos válidos. Reformula tu pedido.")
    plan = _validar_guion_video(raw)
    if not plan["titulos"]:
        raise _PlanError("La IA no propuso títulos. Sé más específico (p. ej. "
                         "'video de inducción: seguridad, puntualidad y revisión de la unidad').")
    return plan
