# rh/templatetags/rh_extras.py

from django import template
from datetime import date, datetime
import locale

# Esta línea es esencial
register = template.Library()

# ============================================
# FUNCIONES PARA CALCULAR ANTIGÜEDAD
# ============================================

def calcular_antiguedad_años_func(fecha_contratacion):
    """
    Calcula solo los años de antigüedad - versión para Python
    """
    if not fecha_contratacion or not isinstance(fecha_contratacion, date):
        return 0
    
    hoy = date.today()
    años = hoy.year - fecha_contratacion.year
    
    # Ajustar si aún no ha cumplido años este año
    if (hoy.month, hoy.day) < (fecha_contratacion.month, fecha_contratacion.day):
        años -= 1
    
    return años


def calcular_antiguedad_completa_func(fecha_contratacion):
    """
    Calcula años y meses de antigüedad - versión para Python
    Retorna un diccionario con años y meses
    """
    if not fecha_contratacion or not isinstance(fecha_contratacion, date):
        return {'años': 0, 'meses': 0, 'texto': 'Sin antigüedad'}
    
    hoy = date.today()
    
    # Calcular años
    años = hoy.year - fecha_contratacion.year
    meses = hoy.month - fecha_contratacion.month
    
    # Ajustar si aún no ha cumplido años este año
    if (hoy.month, hoy.day) < (fecha_contratacion.month, fecha_contratacion.day):
        años -= 1
        meses += 12
    
    # Ajustar meses si es negativo
    if meses < 0:
        meses += 12
    
    # Ajustar por día del mes
    if hoy.day < fecha_contratacion.day:
        meses -= 1
        if meses < 0:
            meses += 12
    
    # Generar texto descriptivo
    if años > 0:
        texto = f"{años} año{'s' if años != 1 else ''}"
        if meses > 0:
            texto += f" {meses} mes{'es' if meses != 1 else ''}"
    elif meses > 0:
        texto = f"{meses} mes{'es' if meses != 1 else ''}"
    else:
        texto = "Menos de 1 mes"
    
    return {
        'años': años,
        'meses': meses,
        'texto': texto
    }


def calcular_dias_vacaciones_func(fecha_contratacion):
    """
    Calcula días de vacaciones según antigüedad
    """
    if not fecha_contratacion or not isinstance(fecha_contratacion, date):
        return 0
    
    antiguedad = calcular_antiguedad_años_func(fecha_contratacion)
    
    # Días según antigüedad
    if antiguedad < 1:
        return 0
    elif antiguedad == 1:
        return 12
    elif antiguedad == 2:
        return 14
    elif antiguedad == 3:
        return 16
    elif antiguedad == 4:
        return 18
    elif antiguedad == 5:
        return 20
    else:
        # 20 días base + 2 días por cada 5 años adicionales
        años_extra = antiguedad - 5
        dias_extra = (años_extra // 5) * 2
        return 20 + dias_extra


# ============================================
# FILTERS PARA TEMPLATES
# ============================================

@register.filter
def calcular_antiguedad_años(fecha_contratacion):
    """
    Calcula solo los años de antigüedad - para templates
    """
    return calcular_antiguedad_años_func(fecha_contratacion)


@register.filter
def calcular_antiguedad(fecha_contratacion):
    """
    Calcula años y meses de antigüedad - para templates
    Retorna string formateado
    """
    resultado = calcular_antiguedad_completa_func(fecha_contratacion)
    return resultado['texto']


@register.filter
def calcular_antiguedad_meses(fecha_contratacion):
    """
    Calcula los meses restantes después de los años
    """
    resultado = calcular_antiguedad_completa_func(fecha_contratacion)
    return resultado['meses']


@register.filter
def calcular_dias_vacaciones(fecha_contratacion):
    """
    Calcula días de vacaciones según antigüedad - para templates
    """
    return calcular_dias_vacaciones_func(fecha_contratacion)


@register.filter
def formato_fecha_es(fecha):
    """
    Formatea una fecha en español
    """
    if not fecha or not isinstance(fecha, (date, datetime)):
        return ""
    
    try:
        # Intentar configurar locale a español
        locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    except:
        # Si falla, usar formato manual
        pass
    
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    # Meses en español
    meses = [
        'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
    ]
    
    # Días de la semana en español
    dias_semana = [
        'lunes', 'martes', 'miércoles', 'jueves', 
        'viernes', 'sábado', 'domingo'
    ]
    
    try:
        dia_semana = dias_semana[fecha.weekday()]
        mes = meses[fecha.month - 1]
        return f"{dia_semana.capitalize()}, {fecha.day} de {mes} de {fecha.year}"
    except:
        # Si algo falla, retornar formato estándar
        return fecha.strftime("%d/%m/%Y")


@register.filter
def edad_actual(fecha_nacimiento):
    """
    Calcula la edad actual en años
    """
    if not fecha_nacimiento or not isinstance(fecha_nacimiento, date):
        return None
    
    hoy = date.today()
    edad = hoy.year - fecha_nacimiento.year
    
    # Ajustar si aún no ha cumplido años este año
    if (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        edad -= 1
    
    return edad


@register.filter
def formato_moneda(valor):
    """
    Formatea un valor como moneda mexicana
    """
    if valor is None:
        return "$0.00"
    
    try:
        valor_float = float(valor)
        return f"${valor_float:,.2f}"
    except (ValueError, TypeError):
        return f"${valor}"


@register.filter
def porcentaje(valor, total):
    """
    Calcula porcentaje y lo formatea
    """
    if not valor or not total or total == 0:
        return "0%"
    
    try:
        porcentaje_val = (float(valor) / float(total)) * 100
        return f"{porcentaje_val:.1f}%"
    except (ValueError, TypeError):
        return "0%"


@register.filter
def get_document_status(vencimiento_date):
    """
    Calcula el estado de un documento basado en su fecha de vencimiento.
    Retorna un diccionario con el color del semáforo y los días restantes.
    """
    if not isinstance(vencimiento_date, date):
        return None

    today = date.today()
    days_remaining = (vencimiento_date - today).days

    if days_remaining <= 10:
        color = 'danger'  # Rojo
        status_text = f"Vence en {days_remaining} día(s)"
        if days_remaining < 0:
            status_text = f"Vencido hace {-days_remaining} día(s)"
        elif days_remaining == 0:
            status_text = "Vence Hoy"
    elif days_remaining <= 30:
        color = 'warning'  # Amarillo
        status_text = f"Vence en {days_remaining} días"
    else:
        color = 'success'  # Verde
        status_text = f"Vence en {days_remaining} días"
        
    return {
        'days_remaining': days_remaining,
        'color': color,
        'status_text': status_text
    }


@register.filter
def initials(nombre_completo):
    """
    Obtiene las iniciales de un nombre completo
    """
    if not nombre_completo:
        return "??"
    
    partes = nombre_completo.split()
    if len(partes) >= 2:
        return f"{partes[0][0]}{partes[1][0]}".upper()
    elif len(partes) == 1:
        return partes[0][:2].upper()
    else:
        return "??"


@register.filter
def truncate_chars(value, max_length):
    """
    Trunca un texto a un máximo de caracteres
    """
    if not value:
        return ""
    
    if len(value) <= max_length:
        return value
    
    return value[:max_length] + "..."


@register.filter
def class_name(obj):
    """
    Retorna el nombre de la clase de un objeto
    """
    return obj.__class__.__name__


@register.filter
def dict_get(dictionary, key):
    """
    Obtiene un valor de un diccionario usando una key
    """
    return dictionary.get(key, "")


@register.filter
def multiply(value, arg):
    """
    Multiplica un valor por otro
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def divide(value, arg):
    """
    Divide un valor por otro
    """
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def add_days(fecha, dias):
    """
    Agrega días a una fecha
    """
    if not fecha or not isinstance(fecha, (date, datetime)):
        return None
    
    try:
        dias_int = int(dias)
        if isinstance(fecha, datetime):
            from datetime import timedelta
            return fecha + timedelta(days=dias_int)
        else:
            from datetime import timedelta
            return fecha + timedelta(days=dias_int)
    except (ValueError, TypeError):
        return fecha


@register.filter
def is_future(fecha):
    """
    Verifica si una fecha es futura
    """
    if not fecha or not isinstance(fecha, (date, datetime)):
        return False
    
    hoy = date.today()
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    return fecha > hoy


@register.filter
def is_past(fecha):
    """
    Verifica si una fecha es pasada
    """
    if not fecha or not isinstance(fecha, (date, datetime)):
        return False
    
    hoy = date.today()
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    return fecha < hoy


@register.filter
def is_today(fecha):
    """
    Verifica si una fecha es hoy
    """
    if not fecha or not isinstance(fecha, (date, datetime)):
        return False
    
    hoy = date.today()
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    
    return fecha == hoy


# ============================================
# SIMPLE TAGS
# ============================================

@register.simple_tag
def get_antiguedad_completa(fecha_contratacion):
    """
    Obtiene antigüedad completa con años y meses (para templates)
    """
    resultado = calcular_antiguedad_completa_func(fecha_contratacion)
    return resultado['texto']


@register.simple_tag
def get_dias_vacaciones_empleado(empleado):
    """
    Calcula días de vacaciones para un empleado
    """
    if not empleado or not empleado.fecha_contratacion:
        return 0
    
    return calcular_dias_vacaciones_func(empleado.fecha_contratacion)


@register.simple_tag
def current_date(format_string="%d/%m/%Y"):
    """
    Retorna la fecha actual formateada
    """
    return datetime.now().strftime(format_string)


@register.simple_tag
def current_year():
    """
    Retorna el año actual
    """
    return datetime.now().year


# ============================================
# INCLUSION TAGS (para templates reutilizables)
# ============================================

@register.inclusion_tag('rh/tags/empleado_badge.html')
def empleado_badge(empleado, size="md"):
    """
    Crea un badge de empleado con avatar y info
    """
    if not empleado:
        return {}
    
    return {
        'empleado': empleado,
        'size': size,
        'iniciales': initials(f"{empleado.nombre} {empleado.apellido}"),
        'antiguedad': calcular_antiguedad_completa_func(empleado.fecha_contratacion)['texto']
    }


@register.inclusion_tag('rh/tags/document_status.html')
def document_status(documento):
    """
    Muestra el estado de un documento
    """
    if not documento or not documento.fecha_vencimiento:
        return {'status': None}
    
    status = get_document_status(documento.fecha_vencimiento)
    return {
        'status': status,
        'documento': documento
    }


# ============================================
# ASIGNATION TAGS (para asignar variables en templates)
# ============================================

@register.simple_tag(takes_context=True)
def set_antiguedad_variable(context, fecha_contratacion, var_name):
    """
    Asigna el cálculo de antigüedad a una variable en el contexto
    """
    resultado = calcular_antiguedad_completa_func(fecha_contratacion)
    context[var_name] = resultado
    return ""