"""
Motor de chat IA del asistente del sistema 3R Recycling.

Diseño:
  - `KNOWLEDGE_BASE` define qué módulos existen, qué hacen, cómo usarlos.
  - `INTENTS` define patrones de pregunta (sinónimos, frases sueltas, palabras
    clave) y mapea cada uno a un manejador.
  - `responder(mensaje, user)` es el ENTRY POINT. Hace match contra los
    intents y compone una respuesta personalizada con el conocimiento.

Motor de IA:
  - `responder_ia(mensaje, user, historial)` es el ENTRY POINT nuevo: usa
    Gemini (tier GRATIS de Google) pasando `KNOWLEDGE_BASE` como contexto, con
    memoria de conversación y filtrado por PERMISOS (solo módulos que el usuario
    puede abrir). Si no hay GEMINI_API_KEY o Gemini falla, cae automáticamente a
    `responder()` (motor por reglas), que TAMBIÉN respeta los permisos.
  - La key sale de la variable de entorno GEMINI_API_KEY (misma que usa el
    resto de la IA de 3r en `ia_studio`).
"""
from __future__ import annotations
import os
import re
import unicodedata


# ════════════════════════════════════════════════════════════════════════════
# BASE DE CONOCIMIENTO
# ════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_BASE = {
    "sistema": {
        "nombre": "3R Recycling — Plataforma ERP",
        "descripcion": (
            "Sistema integral para la operación de 3R Recycling. Maneja remisiones, "
            "viajes, control de diésel, finanzas, RH y catálogos."
        ),
        "modulos": [
            "Dashboard / Mando Central",
            "Remisiones (logística de materiales)",
            "Viajes / Cartas de Traslado",
            "Control Diésel (combustible)",
            "Liquidaciones de Operador",
            "Flujo Bancario / Finanzas",
            "Trane / Manifiestos",
            "Recursos Humanos (Empleados, Vacaciones, Préstamos)",
            "Catálogos Centrales (Empresas, Lugares, Materiales…)",
            "Administración (Permisos, Alertas, Centro de Alertas)",
            "Perfil del Usuario (Preferencias visuales)",
        ],
    },

    "remisiones": {
        "que_es": (
            "Una remisión es el registro logístico de un viaje de materiales entre "
            "un origen y un destino. Incluye carga, descarga, materiales, pesos, "
            "operador, unidad, contenedor, evidencias fotográficas y opcional "
            "destrucción fiscal."
        ),
        "como_crear": [
            "Ir al módulo Remisiones desde el menú lateral",
            "Clic en 'Nueva Remisión'",
            "Llenar empresa, fecha, operador, unidad, contenedor (texto libre)",
            "Elegir origen y destino",
            "Agregar uno o más materiales con peso de carga y descarga",
            "Subir evidencias (PDFs, imágenes)",
            "Si aplica destrucción fiscal, llenar el modal con fotos + material",
            "Guardar — recibe folio automático",
        ],
        "tips": [
            "El folio Medline es automático para remisiones MEDLINE con cartón/archivo",
            "Si la merma supera el umbral configurado, se manda un correo de alerta automático",
            "Las remisiones AUDITADO o CANCELADO no se pueden editar",
            "Puedes generar un Reporte Word de destrucción fiscal cuando los datos están completos",
            "Puedes exportar las remisiones MEDLINE a un ZIP con todas las boletas",
        ],
        "ruta": "/remisiones",
    },

    "viajes": {
        "que_es": (
            "Bitácora de viajes para generar Cartas de Traslado (sin timbrar SAT). "
            "Cada viaje tiene operador, unidad, origen, destino, paradas, mercancía "
            "y sueldo del operador."
        ),
        "como_crear": [
            "Entrar a /viajes y dar 'Nuevo Viaje'",
            "Elegir operador, unidad, origen y destino",
            "Agregar paradas intermedias si aplica",
            "Capturar mercancía: clave SAT, descripción, cantidad, peso",
            "Llenar Eco. Remolque y Placa Remolque si aplica",
            "Guardar — se genera ID interno V-000XXX",
            "Descargar el PDF de Carta de Traslado desde la lista o el detalle",
        ],
        "tips": [
            "El PDF tiene tablas anchas y datos completos: cliente, autotransporte, ubicaciones, mercancía",
            "El folio Carta de Traslado (CT-000XXX) se asigna por número de viaje",
            "Puedes asignar sueldo del operador desde el detalle del viaje",
        ],
        "ruta": "/viajes",
    },

    "diesel": {
        "que_es": (
            "Control de combustible: bitácora de cargas a unidades, compras de diésel, "
            "ajustes de inventario y dashboard en tiempo real por sucursal."
        ),
        "como_crear": [
            "Cargar diésel a una unidad: /diesel/cargas → Nueva Carga",
            "Llenar unidad, kilometraje, litros de diésel/thermo/urea",
            "Capturar cinchos anteriores y actuales (trazabilidad)",
            "Subir fotos (odómetro, bomba, thermo, horas thermo) — todas opcionales",
            "Guardar — descuenta automáticamente del Totem del patio",
        ],
        "tips": [
            "Las compras suman al Totem, las cargas restan — el dashboard refleja el nivel real",
            "Cada carga calcula automáticamente el rendimiento Km/L respecto a la carga anterior",
            "Puedes ver consumo histórico por unidad y por sucursal",
        ],
        "ruta": "/diesel",
    },

    "liquidaciones": {
        "que_es": (
            "Pago a los operadores por sus viajes. Suma sueldos de cada viaje en el "
            "rango, más bonos, menos descuentos y préstamos."
        ),
        "como_crear": [
            "Entrar a /liquidaciones → Nueva Liquidación",
            "Elegir operador y rango de fechas",
            "Se listan automáticamente los viajes pendientes de liquidar",
            "Agregar conceptos manuales (bonos, descuentos, préstamos)",
            "Guardar y generar PDF de liquidación",
        ],
        "ruta": "/liquidaciones",
    },

    "rh": {
        "que_es": (
            "Recursos Humanos: empleados, departamentos, puestos, vacaciones, "
            "préstamos y documentos del operador."
        ),
        "como_crear": [
            "Crear empleado: /rh/empleados → Nuevo",
            "Llenar datos personales, dirección, referencias",
            "Capturar puesto, departamento, supervisor",
            "Elegir División Operativa (chips) y Lugar de operación (combobox)",
            "Agregar contratos, salarios, hijos, historial laboral",
            "Subir documentos del operador (licencia, etc.) si aplica",
            "Guardar — recibe número de empleado automático",
        ],
        "ruta": "/rh/empleados",
    },

    "perfil": {
        "que_es": (
            "Tu perfil de usuario: información personal, contraseña y preferencias "
            "visuales (tipografía, color de acento, modo oscuro)."
        ),
        "como_usar": [
            "Tipo de letra: elige entre 7 tipografías (Sistema, Poppins, Nunito, Raleway, Playfair, Space Grotesk, Mono)",
            "Color de acento: define el color principal del sistema. La barra superior se pinta con un gradiente derivado",
            "Comportamiento en modo oscuro: 'Mantener color de acento' o 'Modo black en todo' (barras grandes oscuras para legibilidad)",
            "Restablecer/Restaurar default: vuelve a fuente Sistema + azul original + modo claro + Modo black en todo activo",
        ],
        "ruta": "/perfil",
    },

    "centro_alertas": {
        "que_es": (
            "Mensajes y notificaciones del sistema. Solo usuarios STAFF pueden ver "
            "y crear alertas. Aparecen en la campana del header (en rojo cuando hay "
            "no leídas) y en /admin/centro-alertas."
        ),
        "como_usar": [
            "Crear alerta: /admin/centro-alertas → Nueva alerta (solo Staff)",
            "Elegir tipo: Crítica, Advertencia, Informativa, Éxito, Neural",
            "Marcar como leído desde la campana o el admin",
            "Eliminar desde cualquiera de los dos lugares",
            "Pestañas: 'No Leídas' y 'Leídas' separan el flujo",
        ],
        "ruta": "/admin/centro-alertas",
    },

    "permisos": {
        "que_es": (
            "Administración de permisos por usuario y por grupo. Solo superuser puede "
            "acceder. Define a qué módulos puede entrar cada cuenta."
        ),
        "ruta": "/admin/permisos",
    },

    "alertas_merma": {
        "que_es": (
            "Configuración de umbrales de merma por material. Cuando una remisión "
            "supera el umbral, se manda UN correo de alerta a los destinatarios "
            "configurados. El correo trae todos los datos de la remisión."
        ),
        "tips": [
            "Configura el umbral en % por cada material",
            "Agrega los correos de quién debe recibir las alertas",
            "Solo se manda 1 correo por remisión — aunque se edite, no re-envía",
        ],
        "ruta": "/admin/alertas-merma",
    },

    "atajos": {
        "como_usar": [
            "Ctrl + K: abre la paleta de comandos (búsqueda rápida de módulos)",
            "F5 o Ctrl + R: refrescar la página",
            "Click en el avatar superior derecho: tu perfil y menú de sesión",
            "Click en la campana: Centro de Alertas (si eres staff)",
            "Menú lateral: colapsable con el botón hamburguesa",
            "Modo oscuro/claro: botón Sol/Luna en el header",
        ],
    },
}


# ════════════════════════════════════════════════════════════════════════════
# PERMISOS — qué módulos puede CONOCER cada usuario
# ════════════════════════════════════════════════════════════════════════════
# Nombre visible de cada módulo gateado (para el resumen "¿qué módulos hay?").
MODULO_TITULO = {
    "remisiones": "Remisiones (logística de materiales)",
    "viajes": "Bitácora de Viajes / Cartas de Traslado",
    "diesel": "Control Diésel (combustible)",
    "liquidaciones": "Liquidaciones de Operador",
    "rh": "Recursos Humanos (Empleados, Vacaciones, Préstamos)",
    "centro_alertas": "Centro de Alertas",
    "alertas_merma": "Alertas de Merma",
    "permisos": "Permisos de Usuario",
    "perfil": "Mi Perfil (preferencias visuales)",
}

# Orden de presentación de los módulos.
_ORDEN_MODULOS = ["remisiones", "viajes", "diesel", "liquidaciones", "rh",
                  "centro_alertas", "permisos", "alertas_merma", "perfil", "atajos"]


def _modulos_permitidos(user) -> set:
    """Claves de KNOWLEDGE_BASE que ESTE usuario puede conocer, con el MISMO
    criterio que `useAllowedMenuIds`/`canAccessPath` del frontend
    (lib/UserContext.tsx). El asistente NO debe explicar ni guiar a un módulo
    fuera de este conjunto.

    - Superuser: todo.
    - Universales (siempre): overview del sistema, perfil y atajos.
    - El resto se abre por el permiso `acceso_*` correspondiente.
    """
    if getattr(user, "is_superuser", False):
        return set(KNOWLEDGE_BASE.keys())

    permitidos = {"sistema", "perfil", "atajos"}

    def _perm(*perms):
        return any(user.has_perm(p) for p in perms)

    if _perm("ternium.acceso_remisiones", "ternium.view_remision"):
        permitidos.add("remisiones")
    if _perm("ternium.acceso_viajes"):
        permitidos.add("viajes")
    if _perm("ternium.acceso_diesel"):
        permitidos.add("diesel")
    if _perm("ternium.acceso_viajes", "ternium.acceso_liquidaciones"):
        permitidos.add("liquidaciones")
    if getattr(user, "is_staff", False):
        permitidos.add("centro_alertas")
    # rh, permisos y alertas_merma quedan solo para superuser (retornado arriba).
    return permitidos


# ════════════════════════════════════════════════════════════════════════════
# UTILIDADES DE NORMALIZACIÓN
# ════════════════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    """Minúsculas, sin acentos, espacios colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^\w\s]', ' ', s.lower())
    return ' '.join(s.split())


def _contiene_alguna(texto: str, palabras: list[str]) -> bool:
    """True si `texto` (normalizado) contiene alguna de las `palabras` (normalizadas)."""
    t = _norm(texto)
    return any(_norm(p) in t for p in palabras)


# ════════════════════════════════════════════════════════════════════════════
# INTENTS — patrones → manejadores
# ════════════════════════════════════════════════════════════════════════════

def _bullets(items: list[str]) -> str:
    return "\n".join(f"  • {x}" for x in items)


def _saludo(_msg: str, user) -> str:
    nombre = (user.get_full_name() or user.username or "").split()[0] or "amigo"
    permitidos = _modulos_permitidos(user)
    ejemplos = ["¿Qué módulos tengo disponibles?"]
    if "remisiones" in permitidos:
        ejemplos.append("¿Cómo creo una remisión?")
    if "diesel" in permitidos:
        ejemplos.append("¿Cómo registro una carga de diésel?")
    if "viajes" in permitidos:
        ejemplos.append("¿Cómo genero una carta de traslado?")
    if "liquidaciones" in permitidos:
        ejemplos.append("¿Cómo hago una liquidación?")
    ejemplos.append("¿Cómo cambio el color del sistema?")
    return (
        f"¡Hola, {nombre}! 👋 Soy el **Asistente 3R**, la inteligencia del sistema.\n\n"
        f"Puedo explicarte los módulos a los que tienes acceso y cómo usarlos.\n\n"
        f"💡 Algunas cosas que puedes preguntarme:\n"
        f"{_bullets(ejemplos[:6])}"
    )


def _modulos(_msg: str, user) -> str:
    sis = KNOWLEDGE_BASE["sistema"]
    permitidos = _modulos_permitidos(user)
    nombres = [MODULO_TITULO[k] for k in _ORDEN_MODULOS
               if k in permitidos and k in MODULO_TITULO]
    if not nombres:
        nombres = [MODULO_TITULO["perfil"]]
    return (
        f"**{sis['nombre']}** — estos son los módulos a los que **tú** tienes acceso:\n\n"
        f"{_bullets(nombres)}\n\n"
        f"Pregúntame por cualquiera de ellos para ver el detalle y cómo usarlo."
    )


def _hacer_modulo(nombre_clave: str):
    """Generador de handler para un módulo específico."""
    def _handler(_msg: str, _user) -> str:
        m = KNOWLEDGE_BASE[nombre_clave]
        partes = [f"📌 **{nombre_clave.upper().replace('_', ' ')}**\n"]
        if "que_es" in m:
            partes.append(f"{m['que_es']}\n")
        if "como_crear" in m:
            partes.append("**Cómo crear:**")
            partes.append(_bullets(m["como_crear"]) + "\n")
        if "como_usar" in m:
            partes.append("**Cómo usar:**")
            partes.append(_bullets(m["como_usar"]) + "\n")
        if "tips" in m:
            partes.append("💡 **Tips:**")
            partes.append(_bullets(m["tips"]) + "\n")
        if "ruta" in m:
            partes.append(f"🔗 Ruta: `{m['ruta']}`")
        return "\n".join(partes)
    return _handler


def _atajos(_msg: str, _user) -> str:
    return (
        "⌨️ **Atajos y trucos del sistema:**\n\n"
        + _bullets(KNOWLEDGE_BASE["atajos"]["como_usar"])
    )


def _ayuda_general(_msg: str, _user) -> str:
    return (
        "🤖 Soy tu asistente del sistema 3R Recycling.\n\n"
        "**Puedo ayudarte con:**\n"
        "  • Información sobre cualquier módulo\n"
        "  • Cómo realizar tareas paso a paso\n"
        "  • Atajos y tips del sistema\n"
        "  • Resolución de dudas operativas\n\n"
        "**Prueba preguntarme:**\n"
        "  • \"¿Cómo creo una remisión?\"\n"
        "  • \"¿Para qué sirve el módulo de viajes?\"\n"
        "  • \"¿Cómo cambio mi color del sistema?\"\n"
        "  • \"¿Qué módulos hay?\"\n"
        "  • \"Atajos de teclado\""
    )


# Lista de intents (orden importa: se evalúa de arriba a abajo, se queda con el primer match).
INTENTS = [
    # Saludos
    {
        "palabras": ["hola", "hey", "buenas", "saludos", "buenos dias", "buenas tardes", "buenas noches"],
        "handler": _saludo,
    },
    # Lista de módulos
    {
        "palabras": [
            "que modulos", "cuales modulos", "que tiene el sistema", "que hay",
            "lista de modulos", "modulos disponibles", "para que sirve el sistema",
        ],
        "handler": _modulos,
    },
    # Remisiones
    {
        "modulo": "remisiones",
        "palabras": ["remision", "remisiones", "carga descarga", "logistica de material"],
        "handler": _hacer_modulo("remisiones"),
    },
    # Viajes / Carta de traslado
    {
        "modulo": "viajes",
        "palabras": ["viaje", "viajes", "carta de traslado", "carta traslado", "ct-"],
        "handler": _hacer_modulo("viajes"),
    },
    # Diesel
    {
        "modulo": "diesel",
        "palabras": ["diesel", "diésel", "combustible", "totem", "tótem", "urea"],
        "handler": _hacer_modulo("diesel"),
    },
    # Liquidaciones
    {
        "modulo": "liquidaciones",
        "palabras": ["liquidacion", "liquidaciones", "pago operador", "sueldo del operador"],
        "handler": _hacer_modulo("liquidaciones"),
    },
    # RH / Empleados
    {
        "modulo": "rh",
        "palabras": ["empleado", "empleados", "rh ", "recursos humanos", "vacaciones", "prestamos"],
        "handler": _hacer_modulo("rh"),
    },
    # Perfil / Preferencias visuales
    {
        "modulo": "perfil",
        "palabras": [
            "perfil", "preferencias", "color del sistema", "color de acento",
            "tipografia", "tipo de letra", "fuente", "modo oscuro", "modo claro", "tema",
        ],
        "handler": _hacer_modulo("perfil"),
    },
    # Centro de alertas
    {
        "modulo": "centro_alertas",
        "palabras": ["alertas", "notificaciones", "centro de alertas", "campana"],
        "handler": _hacer_modulo("centro_alertas"),
    },
    # Permisos
    {
        "modulo": "permisos",
        "palabras": ["permisos", "permiso de usuario", "acceso", "que puede ver"],
        "handler": _hacer_modulo("permisos"),
    },
    # Alertas de merma
    {
        "modulo": "alertas_merma",
        "palabras": ["merma", "alerta merma", "alertas merma", "umbral", "correo merma"],
        "handler": _hacer_modulo("alertas_merma"),
    },
    # Atajos
    {
        "palabras": ["atajo", "atajos", "shortcut", "teclado", "tip", "trucos"],
        "handler": _atajos,
    },
    # Ayuda general (cualquier mención de "ayuda")
    {
        "palabras": ["ayuda", "help", "que puedes hacer", "como te uso", "para que sirves"],
        "handler": _ayuda_general,
    },
]


def _fallback(mensaje: str, user) -> str:
    """Cuando no matcheamos ningún intent, sugerimos SOLO módulos permitidos."""
    permitidos = _modulos_permitidos(user)
    mods = [MODULO_TITULO[k] for k in ("remisiones", "viajes", "diesel", "liquidaciones")
            if k in permitidos]
    sugerencia = ", ".join(mods) if mods else "tu perfil y preferencias visuales"
    return (
        f"No estoy seguro de qué necesitas con: *\"{mensaje[:80]}\"*. 🤔\n\n"
        f"**Puedo ayudarte con los módulos a los que tienes acceso**, por ejemplo:\n"
        f"  • {sugerencia}\n"
        f"  • Atajos de teclado y tus preferencias visuales\n\n"
        f"Escribe **\"¿qué módulos tengo?\"** para ver tu lista, o **\"ayuda\"**."
    )


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def responder(mensaje: str, user) -> str:
    """
    Motor por REGLAS (fallback). Matchea el mensaje contra los intents y
    devuelve una respuesta con el conocimiento del sistema. Respeta permisos:
    NUNCA reconoce un intent de un módulo al que el usuario no tiene acceso.

    Es el respaldo de `responder_ia()` cuando no hay GEMINI_API_KEY o Gemini
    falla, así el asistente jamás se queda sin responder.
    """
    if not mensaje or not mensaje.strip():
        return "Te escucho. ¿En qué te ayudo?"

    permitidos = _modulos_permitidos(user)
    for intent in INTENTS:
        mod = intent.get("modulo")
        if mod and mod not in permitidos:
            continue  # módulo sin acceso: se ignora (no se revela)
        if _contiene_alguna(mensaje, intent["palabras"]):
            return intent["handler"](mensaje, user)

    return _fallback(mensaje, user)


# ════════════════════════════════════════════════════════════════════════════
# MOTOR GEMINI (gratis) — IA conversacional real
# ════════════════════════════════════════════════════════════════════════════
# Mismos modelos flash del tier GRATIS que usa el resto de la IA de 3r
# (ia_studio). El texto de Gemini sí tiene capa gratuita.
GEMINI_CHAT_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.0-flash-001"]


def _gemini_api_key() -> str:
    """Key de Gemini: primero el panel Configuración IA (donde el admin la pega),
    luego variables de entorno del backend (GEMINI_API_KEY / IMAGEN_API_KEY)."""
    try:
        from api.models import ConfiguracionSistema
        k = (ConfiguracionSistema.get_config().imagen_api_key or "").strip()
        if k:
            return k
    except Exception:
        pass
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("IMAGEN_API_KEY") or "").strip()


def _kb_contexto_texto(permitidos: set) -> str:
    """Aplana el KNOWLEDGE_BASE a texto para el system prompt, incluyendo SOLO
    los módulos permitidos para este usuario."""
    bloques = []
    for clave in _ORDEN_MODULOS:
        if clave not in permitidos or clave not in KNOWLEDGE_BASE:
            continue
        m = KNOWLEDGE_BASE[clave]
        titulo = MODULO_TITULO.get(clave, clave.replace("_", " ").title())
        lineas = [f"### {titulo}"]
        if m.get("que_es"):
            lineas.append(m["que_es"])
        if m.get("descripcion"):
            lineas.append(m["descripcion"])
        for campo, etq in (("como_crear", "Cómo hacerlo"),
                           ("como_usar", "Cómo usarlo"),
                           ("tips", "Tips")):
            if m.get(campo):
                lineas.append(f"{etq}:")
                lineas += [f"- {x}" for x in m[campo]]
        if m.get("ruta"):
            lineas.append(f"Ruta en el sistema: {m['ruta']}")
        bloques.append("\n".join(lineas))
    return "\n\n".join(bloques)


def _system_prompt(user, permitidos: set) -> str:
    try:
        nombre = (user.get_full_name() or user.username or "").strip()
    except Exception:
        nombre = ""
    lista = ", ".join(MODULO_TITULO[k] for k in _ORDEN_MODULOS
                      if k in permitidos and k in MODULO_TITULO) or "solo tu perfil"
    kb = _kb_contexto_texto(permitidos)
    return (
        f"Eres el \"Asistente 3R\", la inteligencia integrada del ERP 3R Recycling. "
        f"Ayudas a {nombre or 'el usuario'} a entender y usar el sistema.\n\n"
        "REGLAS ESTRICTAS:\n"
        "- Responde SIEMPRE en español de México, con tono cordial, claro y profesional. Sé conciso.\n"
        "- SOLO puedes hablar de los módulos a los que ESTE usuario tiene acceso (los de abajo). "
        "Si preguntan por un módulo que NO está en tu conocimiento, responde con amabilidad que no "
        "tienen acceso a ese módulo y que lo soliciten a un administrador (Permisos de Usuario); "
        "NO expliques cómo usarlo ni reveles sus detalles.\n"
        "- No inventes módulos, rutas, botones ni funciones que no aparezcan en el conocimiento. "
        "Si no lo sabes, dilo y sugiere a quién preguntar.\n"
        "- Al indicar cómo llegar a un módulo, menciona su ruta (p. ej. /remisiones).\n"
        "- Formato: usa **negritas** para resaltar y viñetas con \"• \" (una por línea). "
        "No uses tablas ni encabezados markdown (#). Respuestas breves salvo que pidan el paso a paso.\n\n"
        f"Módulos a los que ESTE usuario tiene acceso: {lista}.\n\n"
        "=== CONOCIMIENTO DEL SISTEMA (solo lo permitido para este usuario) ===\n"
        f"{kb}"
    )


def _gemini_chat(api_key: str, system: str, historial, mensaje: str) -> str:
    """Llama a Gemini (texto, tier gratis) con memoria de conversación.
    Devuelve el texto de la respuesta o lanza excepción si no hay disponibilidad."""
    from google import genai
    from google.genai import types

    # Timeout duro: evita que una llamada colgada bloquee el worker.
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=40000))

    contents = []
    for h in list(historial or [])[-12:]:  # últimos ~12 turnos: acota tokens/latencia
        if isinstance(h, dict):
            rol = h.get("rol") or h.get("role") or ""
            texto = h.get("contenido") or h.get("content") or ""
        else:
            rol = getattr(h, "rol", "")
            texto = getattr(h, "contenido", "")
        texto = str(texto).strip()
        if not texto:
            continue
        role = "user" if rol == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=texto)]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=str(mensaje))]))

    # Desactivar "thinking" acelera mucho (los flash razonan por defecto). Si el
    # modelo no lo soporta, se reintenta sin ese campo (cfg_simple).
    common = dict(system_instruction=system, temperature=0.4, max_output_tokens=1200)
    try:
        cfg_fast = types.GenerateContentConfig(
            **common, thinking_config=types.ThinkingConfig(thinking_budget=0))
    except Exception:
        cfg_fast = None
    cfg_simple = types.GenerateContentConfig(**common)

    ultimo = None
    for modelo in GEMINI_CHAT_MODELS:
        for cfg in ([cfg_fast, cfg_simple] if cfg_fast else [cfg_simple]):
            try:
                r = client.models.generate_content(model=modelo, contents=contents, config=cfg)
                if r and r.text:
                    return r.text.strip()
                ultimo = ValueError(f"respuesta vacía de {modelo}")
                break
            except Exception as e:
                ultimo = e
                msg = str(e)
                # Sin cuota / modelo inexistente: saltar YA al siguiente modelo.
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg or "NOT_FOUND" in msg or "404" in msg:
                    break
                continue
    raise RuntimeError(f"Gemini no disponible: {ultimo}")


def responder_ia(mensaje: str, user, historial=None) -> str:
    """
    ENTRY POINT del asistente. Usa Gemini (gratis) con el KNOWLEDGE_BASE como
    contexto, memoria de conversación e informado por los PERMISOS del usuario.
    Si no hay GEMINI_API_KEY o Gemini falla por cualquier motivo, cae al motor
    por reglas `responder()` (que también respeta permisos). Nunca lanza.
    """
    if not mensaje or not mensaje.strip():
        return "Te escucho. ¿En qué te ayudo?"

    api_key = _gemini_api_key()
    if not api_key:
        return responder(mensaje, user)  # sin key → motor por reglas

    try:
        permitidos = _modulos_permitidos(user)
        system = _system_prompt(user, permitidos)
        texto = _gemini_chat(api_key, system, historial, mensaje)
        return texto.strip() or responder(mensaje, user)
    except Exception:
        # Cualquier fallo (sin cuota, red, SDK) → motor por reglas.
        return responder(mensaje, user)
