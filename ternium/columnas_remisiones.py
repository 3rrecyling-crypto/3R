# ternium/columnas_remisiones.py
"""Catálogo de columnas de la tabla de remisiones y resolución de la
configuración que cada usuario guarda en su Profile.

La tabla de /remisiones/ tenía 15 columnas fijas escritas a mano en la
plantilla. Aquí viven en un solo sitio para que el <thead>, el <tbody> y el
panel "Personalizar tabla" lean exactamente la misma lista.

Cada columna es un dict con:
    clave     identificador estable que se guarda en la BD (no cambiarlo)
    etiqueta  texto del encabezado
    grupo     sección en la que aparece dentro del panel
    th        clases CSS del <th>
    td        clases CSS del <td>
    style     estilo inline del <th> (los separadores de Carga/Descarga)
    accessor  ruta de atributos para las columnas de valor simple; las que no
              lo traen se pintan con marcado propio en _celda_remision.html
    fija      no se puede ocultar ni mover
    detalle   depende de remision.detalles (van alineadas línea a línea)
"""

# --- Columnas que hoy ya se ven, en su orden actual ------------------------
# El orden de esta lista es el que ve quien nunca ha entrado al panel: la
# página se ve idéntica a como estaba antes de existir esta función.
COLUMNAS = [
    {'clave': 'remision', 'etiqueta': 'Remisión', 'grupo': 'Identificación',
     'th': 'py-3 px-2 col-corta', 'td': 'fw-bold py-3 px-2', 'fija': True},

    {'clave': 'fecha', 'etiqueta': 'Fecha', 'grupo': 'Identificación',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small'},

    {'clave': 'status', 'etiqueta': 'Estatus', 'grupo': 'Identificación',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2'},

    {'clave': 'factura', 'etiqueta': 'Factura', 'grupo': 'Identificación',
     'th': 'py-3 px-2 col-corta text-center', 'td': 'py-3 px-2 text-center'},

    {'clave': 'origen', 'etiqueta': 'Origen', 'grupo': 'Ruta',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small',
     'accessor': 'origen.nombre'},

    {'clave': 'destino', 'etiqueta': 'Destino', 'grupo': 'Ruta',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small',
     'accessor': 'destino.nombre'},

    {'clave': 'material', 'etiqueta': 'Material', 'grupo': 'Material',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'detalle': True},

    {'clave': 'bultos', 'etiqueta': 'Bultos', 'grupo': 'Material',
     'th': 'py-3 px-2 col-corta text-center', 'td': 'py-3 px-2 text-center font-mono',
     'detalle': True},

    {'clave': 'peso_ld', 'etiqueta': 'Peso Carga (Kg)', 'grupo': 'Pesos',
     'th': 'text-end py-3 px-2 col-equitativa', 'style': 'border-left: 2px solid #dee2e6;',
     'td': 'text-end py-3 px-2', 'td_style': 'border-left: 2px solid #dee2e6;',
     'detalle': True},

    {'clave': 'folio_ld', 'etiqueta': 'Folio Carga', 'grupo': 'Pesos',
     'th': 'py-3 px-2 text-primary col-equitativa text-center',
     'td': 'py-3 px-2 fw-bold text-secondary text-center align-middle', 'accessor': 'folio_ld'},

    {'clave': 'peso_dlv', 'etiqueta': 'Peso Descarga (Kg)', 'grupo': 'Pesos',
     'th': 'text-end py-3 px-2 col-equitativa', 'style': 'border-left: 1px solid #dee2e6;',
     'td': 'text-end py-3 px-2', 'td_style': 'border-left: 1px solid #dee2e6;',
     'detalle': True},

    {'clave': 'folio_dlv', 'etiqueta': 'Folio Descarga', 'grupo': 'Pesos',
     'th': 'py-3 px-2 text-primary col-equitativa text-center',
     'td': 'py-3 px-2 fw-bold text-secondary text-center align-middle', 'accessor': 'folio_dlv'},

    {'clave': 'diff', 'etiqueta': 'Dif. (Kg)', 'grupo': 'Pesos',
     'th': 'text-end py-3 px-2 col-corta', 'td': 'text-end py-3 px-2'},

    {'clave': 'merma', 'etiqueta': 'MERMA/A FAVOR', 'grupo': 'Pesos',
     'th': 'text-end py-3 px-2 col-corta text-center', 'td': 'text-end py-3 px-2 text-center fw-bold'},
]

# --- Columnas nuevas: el resto de los datos del formulario de remisión -----
# Son de valor simple, así que se pintan con el accessor y no necesitan
# marcado propio.
COLUMNAS += [
    {'clave': 'empresa', 'etiqueta': 'Empresa', 'grupo': 'Identificación',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'empresa.nombre'},

    {'clave': 'cliente', 'etiqueta': 'Cliente destino', 'grupo': 'Ruta',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'cliente.nombre'},

    {'clave': 'operador', 'etiqueta': 'Operador', 'grupo': 'Transporte',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'operador.nombre'},

    {'clave': 'operador_manual', 'etiqueta': 'Operador (manual)', 'grupo': 'Transporte',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'operador_manual'},

    {'clave': 'linea_transporte', 'etiqueta': 'Línea de transporte', 'grupo': 'Transporte',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'linea_transporte.nombre'},

    {'clave': 'unidad', 'etiqueta': 'Unidad', 'grupo': 'Transporte',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'unidad.nombre'},

    {'clave': 'unidad_manual', 'etiqueta': 'Unidad (manual)', 'grupo': 'Transporte',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'unidad_manual'},

    {'clave': 'contenedor', 'etiqueta': 'Contenedor', 'grupo': 'Transporte',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'contenedor.nombre'},

    {'clave': 'contenedor_manual', 'etiqueta': 'Contenedor (manual)', 'grupo': 'Transporte',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'contenedor_manual'},

    {'clave': 'placas_unidad_manual', 'etiqueta': 'Placas unidad', 'grupo': 'Transporte',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'placas_unidad_manual'},

    {'clave': 'placas_contenedor_manual', 'etiqueta': 'Placas contenedor', 'grupo': 'Transporte',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'placas_contenedor_manual'},

    {'clave': 'inicia_ld', 'etiqueta': 'Inicia carga', 'grupo': 'Tiempos',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'inicia_ld'},

    {'clave': 'termina_ld', 'etiqueta': 'Termina carga', 'grupo': 'Tiempos',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'termina_ld'},

    {'clave': 'inicia_dlv', 'etiqueta': 'Inicia descarga', 'grupo': 'Tiempos',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'inicia_dlv'},

    {'clave': 'termina_dlv', 'etiqueta': 'Termina descarga', 'grupo': 'Tiempos',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'termina_dlv'},

    {'clave': 'hora_entrada', 'etiqueta': 'Hora de entrada', 'grupo': 'Tiempos',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'hora_entrada'},

    {'clave': 'hora_salida', 'etiqueta': 'Hora de salida', 'grupo': 'Tiempos',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'hora_salida'},

    {'clave': 'peso_bascula', 'etiqueta': 'Peso báscula', 'grupo': 'Pesos',
     'th': 'text-end py-3 px-2 col-corta', 'td': 'text-end py-3 px-2 small', 'accessor': 'peso_bascula'},

    {'clave': 'peso_rechazado', 'etiqueta': 'Peso rechazado', 'grupo': 'Pesos',
     'th': 'text-end py-3 px-2 col-corta', 'td': 'text-end py-3 px-2 small',
     'accessor': 'total_peso_rechazado'},

    {'clave': 'factura_nombre', 'etiqueta': 'Folio de factura', 'grupo': 'Identificación',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'factura_nombre'},

    {'clave': 'folio_medline', 'etiqueta': 'Folio Medline', 'grupo': 'Identificación',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'folio_medline'},

    {'clave': 'descripcion', 'etiqueta': 'Descripción', 'grupo': 'Notas',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'descripcion'},

    {'clave': 'comentario', 'etiqueta': 'Comentario', 'grupo': 'Notas',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'comentario'},

    {'clave': 'trazabilidad_notas', 'etiqueta': 'Notas de trazabilidad', 'grupo': 'Notas',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'trazabilidad_notas'},

    {'clave': 'fecha_destruccion', 'etiqueta': 'Fecha de destrucción', 'grupo': 'Destrucción fiscal',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'fecha_destruccion'},

    {'clave': 'destruccion_material_1', 'etiqueta': 'Material destrucción 1', 'grupo': 'Destrucción fiscal',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'destruccion_material_1'},

    {'clave': 'destruccion_peso_1', 'etiqueta': 'Peso destrucción 1', 'grupo': 'Destrucción fiscal',
     'th': 'text-end py-3 px-2 col-corta', 'td': 'text-end py-3 px-2 small', 'accessor': 'destruccion_peso_1'},

    {'clave': 'destruccion_material_2', 'etiqueta': 'Material destrucción 2', 'grupo': 'Destrucción fiscal',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'destruccion_material_2'},

    {'clave': 'destruccion_peso_2', 'etiqueta': 'Peso destrucción 2', 'grupo': 'Destrucción fiscal',
     'th': 'text-end py-3 px-2 col-corta', 'td': 'text-end py-3 px-2 small', 'accessor': 'destruccion_peso_2'},

    {'clave': 'comentarios_destruccion', 'etiqueta': 'Comentarios de destrucción', 'grupo': 'Destrucción fiscal',
     'th': 'py-3 px-3 col-texto', 'td': 'py-3 px-3 small', 'accessor': 'comentarios_destruccion'},

    {'clave': 'auditado_por', 'etiqueta': 'Auditado por', 'grupo': 'Auditoría',
     'th': 'py-3 px-2 col-corta', 'td': 'py-3 px-2 small', 'accessor': 'auditado_por.username'},

    {'clave': 'auditado_en', 'etiqueta': 'Fecha de auditoría', 'grupo': 'Auditoría',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'auditado_en'},

    {'clave': 'creado_en', 'etiqueta': 'Creado en', 'grupo': 'Auditoría',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'creado_en'},

    {'clave': 'actualizado_en', 'etiqueta': 'Actualizado en', 'grupo': 'Auditoría',
     'th': 'py-3 px-2 col-corta', 'td': 'text-nowrap py-3 px-2 small', 'accessor': 'actualizado_en'},
]

# La columna de Acciones nunca entra al catálogo: lleva un <form> con CSRF,
# los permisos de edición y el visor de evidencias. Se pinta siempre al final.

POR_CLAVE = {c['clave']: c for c in COLUMNAS}

# Orden por omisión: las 14 columnas que ya se veían, tal cual estaban.
CLAVES_POR_DEFECTO = [
    'remision', 'fecha', 'status', 'factura', 'origen', 'destino', 'material',
    'bultos', 'peso_ld', 'folio_ld', 'peso_dlv', 'folio_dlv', 'diff', 'merma',
]

CLAVES_FIJAS = [c['clave'] for c in COLUMNAS if c.get('fija')]

# Columnas que se pintan línea por línea a partir de remision.detalles. Están
# alineadas entre sí, así que si el usuario deja alguna hay que conservar
# 'material' como referencia de qué línea es cuál.
CLAVES_DETALLE = [c['clave'] for c in COLUMNAS if c.get('detalle')]

# Relaciones que hay que precargar cuando la columna está activa, para no
# disparar una consulta por fila.
SELECT_RELATED_POR_CLAVE = {
    'empresa': 'empresa',
    'origen': 'origen',
    'destino': 'destino',
    'cliente': 'cliente',
    'operador': 'operador',
    'linea_transporte': 'linea_transporte',
    'unidad': 'unidad',
    'contenedor': 'contenedor',
    'auditado_por': 'auditado_por',
}


def sanear(claves):
    """Deja una lista de claves utilizable: sin desconocidas, sin repetidas y
    con las columnas obligatorias presentes.

    Se aplica tanto al guardar como al leer, porque una configuración vieja
    puede referirse a columnas que ya no existan en el catálogo.
    """
    if not isinstance(claves, (list, tuple)):
        return list(CLAVES_POR_DEFECTO)

    limpias = []
    for clave in claves:
        if isinstance(clave, str) and clave in POR_CLAVE and clave not in limpias:
            limpias.append(clave)

    if not limpias:
        return list(CLAVES_POR_DEFECTO)

    # Las fijas no se pueden perder: si faltan, vuelven al principio.
    for clave in reversed(CLAVES_FIJAS):
        if clave not in limpias:
            limpias.insert(0, clave)

    # 'material' es la referencia de las columnas multilínea; sin ella no se
    # sabe a qué material corresponde cada renglón de bultos o de pesos.
    if 'material' not in limpias and any(c in limpias for c in CLAVES_DETALLE):
        limpias.insert(limpias.index(next(c for c in limpias if c in CLAVES_DETALLE)), 'material')

    return limpias


def config_de(usuario):
    """Lee la configuración guardada de un usuario, tolerando formatos viejos.

    Devuelve (claves_personalizadas, usa_personalizada). Las claves se
    conservan aunque la personalización esté apagada: así el usuario puede ir
    y volver entre su tabla y la de siempre sin rearmarla.
    """
    perfil = getattr(usuario, 'ternium_profile', None)
    guardado = getattr(perfil, 'columnas_remisiones', None) if perfil else None

    if isinstance(guardado, list):
        # Formato anterior: solo la lista de columnas.
        return sanear(guardado), bool(guardado)

    if not isinstance(guardado, dict):
        return list(CLAVES_POR_DEFECTO), False

    claves = guardado.get('columnas')
    personalizada = bool(guardado.get('personalizada')) and bool(claves)
    return sanear(claves) if claves else list(CLAVES_POR_DEFECTO), personalizada


def columnas_por_defecto():
    """Las columnas de siempre, como dicts completos."""
    return [POR_CLAVE[c] for c in CLAVES_POR_DEFECTO]


def columnas_de(usuario):
    """Devuelve las columnas (dicts completos) que se deben pintar ahora."""
    claves, personalizada = config_de(usuario)
    if not personalizada:
        claves = list(CLAVES_POR_DEFECTO)
    return [POR_CLAVE[c] for c in claves]


def formatear(valor):
    """Convierte un valor a texto para mostrarlo en una celda."""
    import datetime
    from decimal import Decimal

    from django.utils import timezone

    if valor is None or valor == '':
        return '-'
    if isinstance(valor, bool):
        return 'Sí' if valor else 'No'
    if isinstance(valor, datetime.datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.strftime('%d/%m/%Y %H:%M')
    if isinstance(valor, datetime.date):
        return valor.strftime('%d/%m/%Y')
    if isinstance(valor, datetime.time):
        return valor.strftime('%H:%M')
    if isinstance(valor, (Decimal, float)):
        return f'{valor:,.3f}'.rstrip('0').rstrip('.')
    return str(valor)


def valor_texto(remision, col):
    """Valor de la celda ya formateado como texto (para la API del frontend)."""
    valor = valor_plano(remision, col)
    if valor == '':
        return '-'
    if isinstance(valor, str):
        return valor
    return formatear(valor)


def _lineas(valores):
    """Un renglón por detalle. Si no hay nada que mostrar, celda vacía."""
    textos = [str(v) for v in valores if v not in (None, '')]
    return '\n'.join(textos) if textos else ''


def _numero_o_lineas(valores):
    """Con un solo detalle devuelve el número (para que Excel pueda sumarlo);
    con varios, un renglón por detalle."""
    limpios = [v for v in valores if v is not None]
    if not limpios:
        return ''
    if len(limpios) == 1:
        return float(limpios[0])
    return '\n'.join(f'{float(v):.2f}' for v in limpios)


def valor_plano(remision, col):
    """Valor de una celda sin HTML, para exportar a Excel.

    Devuelve números como números (para que Excel pueda sumarlos) y el resto
    como texto. Las columnas multilínea salen con un renglón por detalle,
    igual que en pantalla.
    """
    clave = col['clave']

    if clave == 'remision':
        return remision.remision
    if clave == 'fecha':
        return remision.fecha
    if clave == 'status':
        return remision.get_status_display()
    if clave == 'factura':
        return ', '.join(f.folio or str(f.id) for f in remision.facturas.all()) or ''
    if clave == 'material':
        return _lineas((d.material.nombre if d.material else '') for d in remision.detalles.all())
    if clave == 'bultos':
        return _lineas(d.bultos for d in remision.detalles.all())
    if clave == 'peso_ld':
        return _numero_o_lineas([d.peso_ld for d in remision.detalles.all()])
    if clave == 'peso_dlv':
        return _numero_o_lineas([d.peso_dlv for d in remision.detalles.all()])
    if clave == 'diff':
        if remision.status == 'PENDIENTE':
            return ''
        return float(remision.total_peso_dlv or 0) - float(remision.total_peso_ld or 0)
    if clave == 'merma':
        if remision.status == 'PENDIENTE':
            return ''
        return round(float(remision.porcentaje_merma or 0), 2)

    # Columnas simples: se recorre el accessor y se devuelve el valor crudo
    # (fechas y decimales van tal cual para que Excel los reconozca).
    valor = remision
    for tramo in (col.get('accessor') or '').split('.'):
        if valor is None or not tramo:
            return ''
        valor = getattr(valor, tramo, None)
        if callable(valor):
            valor = valor()

    if valor is None:
        return ''

    # Excel no admite fechas con zona horaria.
    import datetime

    from django.utils import timezone

    if isinstance(valor, datetime.datetime) and timezone.is_aware(valor):
        valor = timezone.localtime(valor).replace(tzinfo=None)

    return valor


def catalogo_agrupado(claves_activas):
    """El catálogo listo para el panel: activas primero en su orden guardado,
    después las disponibles agrupadas por sección."""
    activas = [dict(POR_CLAVE[c], activa=True) for c in claves_activas if c in POR_CLAVE]
    inactivas = [dict(c, activa=False) for c in COLUMNAS if c['clave'] not in claves_activas]

    grupos = {}
    for col in inactivas:
        grupos.setdefault(col['grupo'], []).append(col)

    return activas, [{'nombre': n, 'columnas': cols} for n, cols in grupos.items()]
