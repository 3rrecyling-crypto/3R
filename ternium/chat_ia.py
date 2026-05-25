"""
Motor de chat IA del asistente del sistema 3R Recycling.

Diseño:
  - `KNOWLEDGE_BASE` define qué módulos existen, qué hacen, cómo usarlos.
  - `INTENTS` define patrones de pregunta (sinónimos, frases sueltas, palabras
    clave) y mapea cada uno a un manejador.
  - `responder(mensaje, user)` es el ENTRY POINT. Hace match contra los
    intents y compone una respuesta personalizada con el conocimiento.

Para upgradear a IA real (OpenAI, Claude, Gemini, etc.) en el futuro:
  Reemplaza `responder()` por una función que llame a la API externa y
  pase `KNOWLEDGE_BASE` como contexto en el system prompt. Toda la
  infraestructura (modelo, endpoints, UI) ya está en su lugar.
"""
from __future__ import annotations
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
    return (
        f"¡Hola, {nombre}! 👋 Soy el asistente IA de **3R Recycling**.\n\n"
        f"Puedo explicarte cualquier módulo del sistema, cómo usarlo y para qué sirve.\n\n"
        f"💡 Algunas cosas que puedes preguntarme:\n"
        f"  • ¿Qué módulos tiene el sistema?\n"
        f"  • ¿Cómo creo una remisión?\n"
        f"  • ¿Cómo registro una carga de diésel?\n"
        f"  • ¿Cómo cambio el color del sistema?\n"
        f"  • ¿Para qué sirve el Centro de Alertas?"
    )


def _modulos(_msg: str, _user) -> str:
    sis = KNOWLEDGE_BASE["sistema"]
    return (
        f"**{sis['nombre']}** tiene los siguientes módulos:\n\n"
        f"{_bullets(sis['modulos'])}\n\n"
        f"Pregúntame por cualquiera de ellos para más detalle."
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
        "palabras": ["remision", "remisiones", "carga descarga", "logistica de material"],
        "handler": _hacer_modulo("remisiones"),
    },
    # Viajes / Carta de traslado
    {
        "palabras": ["viaje", "viajes", "carta de traslado", "carta traslado", "ct-"],
        "handler": _hacer_modulo("viajes"),
    },
    # Diesel
    {
        "palabras": ["diesel", "diésel", "combustible", "totem", "tótem", "urea"],
        "handler": _hacer_modulo("diesel"),
    },
    # Liquidaciones
    {
        "palabras": ["liquidacion", "liquidaciones", "pago operador", "sueldo del operador"],
        "handler": _hacer_modulo("liquidaciones"),
    },
    # RH / Empleados
    {
        "palabras": ["empleado", "empleados", "rh ", "recursos humanos", "vacaciones", "prestamos"],
        "handler": _hacer_modulo("rh"),
    },
    # Perfil / Preferencias visuales
    {
        "palabras": [
            "perfil", "preferencias", "color del sistema", "color de acento",
            "tipografia", "tipo de letra", "fuente", "modo oscuro", "modo claro", "tema",
        ],
        "handler": _hacer_modulo("perfil"),
    },
    # Centro de alertas
    {
        "palabras": ["alertas", "notificaciones", "centro de alertas", "campana"],
        "handler": _hacer_modulo("centro_alertas"),
    },
    # Permisos
    {
        "palabras": ["permisos", "permiso de usuario", "acceso", "que puede ver"],
        "handler": _hacer_modulo("permisos"),
    },
    # Alertas de merma
    {
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


def _fallback(mensaje: str, _user) -> str:
    """Cuando no matcheamos ningún intent, sugerimos posibles temas."""
    return (
        f"No estoy seguro de qué necesitas con: *\"{mensaje[:80]}\"*. 🤔\n\n"
        f"**Prueba reformular o pregúntame por:**\n"
        f"  • Un módulo específico (remisiones, viajes, diésel, liquidaciones, RH…)\n"
        f"  • Una tarea (\"¿cómo creo X?\", \"¿cómo cambio Y?\")\n"
        f"  • Atajos de teclado\n"
        f"  • \"¿Qué módulos hay?\" para ver el panorama\n\n"
        f"O escribe **\"ayuda\"** para ver lo que puedo hacer."
    )


# ════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def responder(mensaje: str, user) -> str:
    """
    Recibe un mensaje del usuario y devuelve una respuesta.

    Para upgradear a IA real más adelante: reemplaza el cuerpo de esta función
    por una llamada a OpenAI / Anthropic / Gemini, pasando KNOWLEDGE_BASE como
    contexto (system prompt). La infraestructura (modelo ChatMensaje, endpoints,
    UI) ya está preparada y no necesita cambios.
    """
    if not mensaje or not mensaje.strip():
        return "Te escucho. ¿En qué te ayudo?"

    for intent in INTENTS:
        if _contiene_alguna(mensaje, intent["palabras"]):
            return intent["handler"](mensaje, user)

    return _fallback(mensaje, user)
