"""Asistente 3D: convierte el pedido del cliente (texto) en un PLAN de sketch
(JSON) que el modelador 3D del frontend sabe dibujar.

Aislamiento: este módulo SOLO sabe del catálogo del modelador y del cliente de
IA. No importa ni consulta facturación ni ningún otro módulo de negocio, así que
la IA NO tiene acceso a facturación por construcción.
"""
from __future__ import annotations

import json
import math
import re
from typing import Optional

from ia_studio.ia_client import chat_ia

# ── Catálogo válido (debe coincidir con ObjKind del modelador 3D) ──────────────
KINDS = {
    # Vehículos
    "camion", "tracto", "pipa", "pickup", "carro", "van", "autobus", "remolque", "montacargas",
    # Logística de patio
    "contenedor", "palet", "tambo", "tanque", "dispensador", "rack", "llantas", "caja", "bascula", "rampa",
    "anden", "contenedor_basura", "contenedor_apilado", "surtidor_doble", "estacion_lavado",
    "estanteria_selectiva", "dolly",
    # Equipo y maquinaria
    "banda", "maquinaria", "computadora",
    # Industrial y planta
    "silo", "tanque_vert", "cisterna_elev", "grua_portico", "chimenea", "transformador", "generador",
    "tolva", "tuberia", "torre_luz", "escalera", "barandal", "panel_solar", "estacion_ext",
    # Techos y naves
    "nave", "cobertizo", "techo",
    # Oficinas y edificios
    "oficina", "oficina_movil", "caseta", "bano", "caseta_pesaje",
    # Accesos y bardas
    "porton", "puerta", "talanquera",
    # Señalización
    "cono", "barrera", "poste", "alto", "semaforo", "hidrante", "letrero", "tope", "bolardo",
    # Áreas verdes
    "arbol", "arbusto",
    # Personas y mobiliario
    "persona", "mesa", "silla", "maceta", "ventana",
}
TIPOS_BARDA = {"muro", "reja", "malla"}
# Superficies de piso (zonificación del terreno) que el modelador sabe texturizar.
SURFS = {"pasto", "tierra", "grava", "asfalto", "concreto"}

# Descripción del catálogo con huellas (X ancho × Z fondo × Y alto, metros) para
# que el modelo separe los objetos sin encimarlos.
CATALOGO_TXT = """VEHÍCULOS (frente/nariz hacia +Z con rotY=0; estaciónalos con rotY=3.1416 para que la nariz apunte a la salida):
- camion 2.4×6.6 · tracto 2.6×11 · pipa 2.6×11 · pickup 1.9×5 · carro 1.8×4.3 · van 2×4.2 · autobus 2.5×9 · remolque 2.55×12 · montacargas 1.1×2.3
LOGÍSTICA:
- contenedor 2.44×6.06 · palet 1.2×1.1 · tambo 0.6ø · tanque 1.9×3.4 · dispensador 0.7×0.7 · rack 2×1.2 · llantas 0.84ø · caja 1×1 · bascula 3.4×9 (los camiones pasan a lo largo de Z) · rampa 4.5×3 (sube hacia +X)
- anden 12×3 (muelle de carga) · contenedor_basura 1.8×1.2 · contenedor_apilado 2.44×6.06 (2 niveles, ~5.2 alto) · surtidor_doble 6×3 (isla de despacho con techo) · estacion_lavado 5×4 (bahía de lavado) · estanteria_selectiva 3×1.2 (rack alto 6 m, para interiores de nave) · dolly 1×1 (convertidor)
EQUIPO Y MAQUINARIA (para interiores de nave/oficina):
- banda 6×1.2 (transportadora, a lo largo de X) · maquinaria 2.6×1.8 (máquina/CNC) · computadora 1.2×0.6 (estación de trabajo)
INDUSTRIAL Y PLANTA:
- silo 3ø×9 · tanque_vert 3ø×8 · cisterna_elev 4×4 (tanque elevado) · grua_portico 12 ancho · chimenea 1.5ø×12 · transformador 2×2 · generador 4×2 · tolva 3×3 · tuberia 6×2 (rack de tubería) · torre_luz 8 alto (iluminación) · escalera 1×3 · barandal 2 largo · panel_solar 3×2 · estacion_ext 1×0.5 (extintores)
TECHOS Y NAVES:
- nave 12×20 (portón en +Z) · cobertizo 8×12 (techumbre abierta) · techo 8×10
OFICINAS Y EDIFICIOS (puerta/ventanas en +Z):
- oficina 8×8 · oficina_movil 2.5×6 · caseta 1.7×1.7 (vigilancia) · caseta_pesaje 2×2.5 (control/pesaje, junto a la báscula) · bano 1.1×1.1
ACCESOS:
- porton 5.3 ancho (portón corredizo) · puerta 1.2 ancho · talanquera 4 ancho (pluma/barrera de acceso, en el carril de entrada)
SEÑALIZACIÓN:
- cono 0.36 · barrera 0.8×2 · poste 5 alto (luz) · alto (señal) · semaforo · hidrante · letrero 1.7 ancho · tope 3.5 ancho (reductor) · bolardo 0.24ø (protección)
ÁREAS VERDES:
- arbol 2ø×3alto · arbusto 1ø
PERSONAS Y MOBILIARIO:
- persona · mesa 1.4×0.7 · silla · maceta · ventana"""

SYSTEM_PROMPT = f"""Eres un asistente experto que DISEÑA la distribución (layout) de un patio o instalación de transporte/logística en 3D a partir del pedido del cliente, para una empresa mexicana.

Tu única salida es un objeto JSON con este esquema EXACTO (sin texto adicional, sin explicaciones, sin bloques de código markdown):
{{
  "objetos": [ {{ "kind": "<catalogo>", "x": <número>, "z": <número>, "rotY": <radianes>, "scale": <número>, "color": "#RRGGBB (opcional)", "y": <altura opcional para apilar> }} ],
  "bardas":  [ {{ "tipo": "muro|reja|malla", "altura": <metros>, "pts": [[x,z],[x,z], ...] }} ],
  "pisos":   [ {{ "surf": "pasto|tierra|grava|asfalto|concreto", "cx": <número>, "cz": <número>, "w": <ancho m>, "d": <fondo m> }} ],
  "resumen": "<1-2 frases en español de lo que armaste>"
}}

Sistema de coordenadas:
- El suelo es el plano XZ; Y es la altura. Por defecto todo va apoyado en el piso (y=0); el campo opcional "y" se usa SOLO para apilar (ver reglas).
- Usa x ∈ [-45, 45] y z ∈ [-30, 30] (un lote cercado de ~80×60 m). z negativo = frente/entrada, z positivo = fondo.
- rotY en radianes (0, 1.5708, 3.1416, 4.7124). Con rotY=0 el "frente" mira a +Z.
- scale es un factor uniforme (1 normal; usa 0.8–2 si hace falta).

Reglas:
- Usa SOLO estos kind exactos (cualquier otro se descarta):
{CATALOGO_TXT}
- SEPARA los objetos según su huella para que NO se encimen (p.ej. camiones estacionados en fila ~7 m aparte en X; deja pasillos).
- Organiza por zonas lógicas: acceso/control al frente (portón, caseta, báscula, alto), oficinas y estacionamiento a un lado, unidades (camiones) en fila, almacén/nave al fondo, zona de combustible cercada con reja, áreas verdes en el perímetro.
- Cerca el perímetro con una barda (malla ~2.6 m) dejando un hueco al frente (z=-30) para el portón (x≈0).
- ZONIFICA el suelo con "pisos" (3-6 rectángulos): asfalto en acceso y circulación, concreto en oficinas y báscula, grava en la zona de combustible, tierra en el patio de maniobras. El césped base ya existe; los pisos van encima y dan realismo inmediato.
- Cantidades razonables: si el cliente pide "3 camiones", pon 3. Si pide "un patio", arma uno completo y realista.
- "color" (opcional, #RRGGBB): pinta el objeto. Úsalo cuando lo pidan ("camiones de la flota en azul corporativo", zonas por color, resaltar). Sin color = colores por defecto del catálogo.
- "y" (opcional, metros): altura sobre el piso para APILAR. Casi todo va en y=0 (piso). Para apilar contenedores/cajas: 2º nivel y≈2.6, 3º y≈5.2. Úsalo con moderación y solo si aporta.
- Aprovecha el catálogo AMPLIO: para planta/industria usa silo, tanque_vert, cisterna_elev, grua_portico, chimenea, transformador, generador, panel_solar, torre_luz; para logística usa anden, contenedor_apilado, surtidor_doble, estacion_lavado, estanteria_selectiva; para control usa caseta_pesaje y talanquera en el acceso.
- Si te pasan objetos existentes, AGREGA a la escena evitando encimarlos (no repitas lo que ya está salvo que lo pidan).

Responde ÚNICAMENTE con el JSON."""


def _extraer_json(txt: str) -> Optional[dict]:
    """Obtiene el primer objeto JSON del texto (tolera fences ```json ... ```)."""
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
    # Fallback: recorta desde la primera '{' hasta la última '}'.
    i, j = s.find("{"), s.rfind("}")
    if i >= 0 and j > i:
        try:
            d = json.loads(s[i:j + 1])
            return d if isinstance(d, dict) else None
        except Exception:
            return None
    return None


def _num(v, default=0.0):
    """Convierte a float FINITO (descarta NaN/Infinity para no romper el render JSON)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _color_hex(v):
    """Devuelve un hex #RRGGBB válido o None (para el color opcional del objeto)."""
    s = str(v or "").strip()
    return s if _HEX_RE.match(s) else None


def validar_plan(raw: dict) -> dict:
    """Filtra/normaliza el plan crudo del modelo: descarta kinds/tipos inválidos y
    acota coordenadas. Devuelve un plan seguro para el frontend."""
    objetos = []
    _objs = raw.get("objetos")
    for o in (_objs if isinstance(_objs, list) else [])[:400]:
        if not isinstance(o, dict):
            continue
        kind = str(o.get("kind") or "").strip()
        if kind not in KINDS:
            continue
        obj = {
            "kind": kind,
            "x": round(_clamp(_num(o.get("x")), -60, 60), 2),
            "z": round(_clamp(_num(o.get("z")), -45, 45), 2),
            "rotY": round(_num(o.get("rotY")) % (2 * math.pi), 4),  # ya es finito → módulo estable
            "scale": round(_clamp(_num(o.get("scale"), 1) or 1, 0.2, 4), 2),
            "y": round(_clamp(_num(o.get("y")), 0, 20), 2),  # altura sobre el piso (apilar)
        }
        c = _color_hex(o.get("color"))
        if c:
            obj["color"] = c  # color opcional (flota corporativa, zonas)
        objetos.append(obj)
    bardas = []
    _bardas = raw.get("bardas")
    for b in (_bardas if isinstance(_bardas, list) else [])[:40]:
        if not isinstance(b, dict):
            continue
        tipo = str(b.get("tipo") or "").strip()
        pts_raw = b.get("pts") or []
        if tipo not in TIPOS_BARDA or not isinstance(pts_raw, list) or len(pts_raw) < 2:
            continue
        pts = []
        for p in pts_raw[:200]:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                pts.append([round(_clamp(_num(p[0]), -60, 60), 2), round(_clamp(_num(p[1]), -45, 45), 2)])
        if len(pts) >= 2:
            bardas.append({"tipo": tipo, "altura": round(_clamp(_num(b.get("altura"), 2.2) or 2.2, 0.4, 6), 2), "pts": pts})
    pisos = []
    _pisos = raw.get("pisos")
    for p in (_pisos if isinstance(_pisos, list) else [])[:30]:
        if not isinstance(p, dict):
            continue
        surf = str(p.get("surf") or "").strip()
        if surf not in SURFS:
            continue
        pisos.append({
            "surf": surf,
            "cx": round(_clamp(_num(p.get("cx")), -60, 60), 2),
            "cz": round(_clamp(_num(p.get("cz")), -45, 45), 2),
            "w": round(_clamp(_num(p.get("w"), 8) or 8, 1, 120), 2),
            "d": round(_clamp(_num(p.get("d"), 8) or 8, 1, 120), 2),
        })
    return {"objetos": objetos, "bardas": bardas, "pisos": pisos, "resumen": str(raw.get("resumen") or "").strip()[:400]}


def generar_sketch(pedido: str, objetos_existentes: list, cfg: dict, imagenes=None) -> dict:
    """Llama al proveedor de IA y devuelve un plan validado. `cfg` = salida de
    resolver_config_ia(). `imagenes` = fotos opcionales (visión). Lanza IAError."""
    partes = [f"Pedido del cliente:\n{pedido.strip()}"]
    if imagenes:
        partes.append("El cliente adjuntó una o más FOTOS de referencia (un patio, "
                      "un croquis o una instalación real). Básate en ellas para el layout.")
    if objetos_existentes:
        resumen = ", ".join(
            f"{e.get('kind')}({round(_num(e.get('x')),1)},{round(_num(e.get('z')),1)})"
            for e in objetos_existentes[:120] if e.get("kind")
        )
        partes.append("Objetos que YA existen en la escena (no los encimes; agrega alrededor):\n" + resumen)
    user_prompt = "\n\n".join(partes)

    texto = chat_ia(
        proveedor=cfg["proveedor"], api_key=cfg["api_key"],
        base_url=cfg["base_url"], modelo=cfg["modelo"],
        system=SYSTEM_PROMPT, user=user_prompt,
        max_tokens=6000, temperature=0.5, json_mode=True,
        imagenes=imagenes,
    )
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió un plan válido. Intenta reformular tu pedido.")
    plan = validar_plan(raw)
    if not plan["objetos"] and not plan["bardas"] and not plan["pisos"]:
        raise _PlanError("La IA no propuso objetos. Sé más específico (p. ej. '3 camiones, una nave y oficinas').")
    return plan


class _PlanError(Exception):
    """Error legible cuando el plan no es utilizable."""


# ══════════════════ EDITAR la escena por instrucción (ops) ══════════════════
# El cliente pide cambios en lenguaje natural ("mueve los camiones junto a la
# nave, borra los conos, pinta la flota de azul") y la IA devuelve OPS sobre los
# ids existentes — no recrea la escena. Mismo patrón probado del Canvas.
SYSTEM_PROMPT_EDITAR = f"""Eres un asistente que EDITA una escena 3D existente de un patio/instalación de transporte (México) según la instrucción del cliente.

Recibes la lista de objetos ACTUALES (JSON: id, kind, x, z, rotY, scale, nombre) y una instrucción. Tu única salida es un objeto JSON con este esquema EXACTO (sin texto extra, sin markdown):
{{
  "ops": [
    {{ "op": "update", "id": "<id existente>", "cambios": {{ "x": <n>, "z": <n>, "y": <n>, "rotY": <rad>, "scale": <n>, "color": "#RRGGBB" }} }},
    {{ "op": "delete", "id": "<id existente>" }},
    {{ "op": "duplicate", "id": "<id existente>", "dx": <n>, "dz": <n>, "count": <n> }},
    {{ "op": "add", "objeto": {{ "kind": "<catalogo>", "x": <n>, "z": <n>, "rotY": <rad>, "scale": <n>, "color": "#RRGGBB opc", "y": <opc> }} }},
    {{ "op": "add_barda", "tipo": "muro|reja|malla", "altura": <m>, "pts": [[x,z],[x,z],...] }},
    {{ "op": "add_piso", "surf": "pasto|tierra|grava|asfalto|concreto", "cx": <n>, "cz": <n>, "w": <m>, "d": <m> }}
  ],
  "resumen": "<1 frase en español de lo que hiciste>"
}}

Sistema de coordenadas: suelo = plano XZ (x ∈ [-45,45], z ∈ [-30,30]; z negativo = frente/entrada); Y = altura (solo para apilar); rotY en radianes (con rotY=0 el frente mira a +Z).

Catálogo para "add" (usa SOLO estos kind, con su huella ancho×fondo):
{CATALOGO_TXT}

Reglas:
- Cambia SOLO lo que pide la instrucción: usa "update" sobre los ids EXISTENTES (mueve/rota/escala/pinta), "delete" para quitar, "duplicate" para repetir uno existente (count copias separadas dx/dz según su huella) y "add" para cosas nuevas.
- "en cada uno / todos los camiones" → una op por cada id que aplique (fíjate en kind y nombre).
- Al mover/agregar respeta las huellas para NO encimar objetos, y mantén pasillos de circulación.
- "color" pinta el objeto completo (#RRGGBB). Para des-pintar no hay op: no lo inventes.
- Máximo ~120 ops. Si la instrucción no es editable (p. ej. pregunta general), devuelve ops vacío y explícalo en "resumen".

Responde ÚNICAMENTE con el JSON."""


def validar_ops(raw: dict, ids: set) -> list:
    """Filtra/normaliza las ops del modelo: solo ids existentes, kinds del
    catálogo y geometría acotada. Reusa validar_plan para los add_*."""
    ops = []
    _ops = raw.get("ops")
    for o in (_ops if isinstance(_ops, list) else [])[:200]:
        if not isinstance(o, dict):
            continue
        kind = str(o.get("op") or "").strip()
        if kind == "update":
            oid = str(o.get("id") or "").strip()
            if oid not in ids:
                continue
            c = o.get("cambios") if isinstance(o.get("cambios"), dict) else {}
            out = {}
            for k, lo, hi in (("x", -60, 60), ("z", -45, 45), ("y", 0, 20)):
                if c.get(k) is not None:
                    out[k] = round(_clamp(_num(c.get(k)), lo, hi), 2)
            if c.get("rotY") is not None:
                out["rotY"] = round(_num(c.get("rotY")) % (2 * math.pi), 4)
            if c.get("scale") is not None:
                out["scale"] = round(_clamp(_num(c.get("scale"), 1) or 1, 0.2, 4), 2)
            col = _color_hex(c.get("color"))
            if col:
                out["color"] = col
            if out:
                ops.append({"op": "update", "id": oid, "cambios": out})
        elif kind == "delete":
            oid = str(o.get("id") or "").strip()
            if oid in ids:
                ops.append({"op": "delete", "id": oid})
        elif kind == "duplicate":
            oid = str(o.get("id") or "").strip()
            if oid in ids:
                ops.append({"op": "duplicate", "id": oid,
                            "dx": round(_clamp(_num(o.get("dx"), 3), -60, 60), 2),
                            "dz": round(_clamp(_num(o.get("dz"), 0), -45, 45), 2),
                            "count": int(_clamp(_num(o.get("count"), 1) or 1, 1, 20))})
        elif kind == "add":
            objs = validar_plan({"objetos": [o.get("objeto") or {}]})["objetos"]
            if objs:
                ops.append({"op": "add", "objeto": objs[0]})
        elif kind == "add_barda":
            bs = validar_plan({"bardas": [o]})["bardas"]
            if bs:
                ops.append({"op": "add_barda", **bs[0]})
        elif kind == "add_piso":
            ps = validar_plan({"pisos": [o]})["pisos"]
            if ps:
                ops.append({"op": "add_piso", **ps[0]})
    return ops


def editar_sketch(instruccion: str, objetos: list, cfg: dict, imagenes=None) -> dict:
    """Edita la escena existente vía ops. `objetos` = [{id,kind,x,z,rotY,scale,nombre}]."""
    resumen = []
    ids = set()
    for e in (objetos or [])[:250]:
        if not isinstance(e, dict):
            continue
        oid = str(e.get("id") or "").strip()
        if not oid:
            continue
        ids.add(oid)
        resumen.append({
            "id": oid,
            "kind": str(e.get("kind") or "objeto")[:30],
            "x": round(_num(e.get("x")), 1), "z": round(_num(e.get("z")), 1),
            "rotY": round(_num(e.get("rotY")), 3),
            "scale": round(_num(e.get("scale"), 1) or 1, 2),
            "nombre": str(e.get("nombre") or "")[:40],
        })
    user = (f"Objetos actuales de la escena (JSON):\n{json.dumps(resumen, ensure_ascii=False)}\n\n"
            f"Instrucción del cliente:\n{instruccion.strip()}")
    if imagenes:
        user += "\n\nEl cliente adjuntó foto(s) de referencia; úsalas para entender el cambio."
    texto = chat_ia(
        proveedor=cfg["proveedor"], api_key=cfg["api_key"],
        base_url=cfg["base_url"], modelo=cfg["modelo"],
        system=SYSTEM_PROMPT_EDITAR, user=user,
        max_tokens=6000, temperature=0.3, json_mode=True,
        imagenes=imagenes,
    )
    raw = _extraer_json(texto)
    if not raw:
        raise _PlanError("La IA no devolvió cambios válidos. Reformula tu pedido.")
    ops = validar_ops(raw, ids)
    return {"ops": ops, "resumen": str(raw.get("resumen") or "").strip()[:400]}
