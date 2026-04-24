# RH/templatetags/filters_extras.py
from django import template
from datetime import datetime, date, timedelta
import calendar
from decimal import Decimal, InvalidOperation
import sys

print("=" * 50)
print("FILTERS_EXTRAS.PY se está cargando...")
print(f"Desde: {__file__}")
print(f"Python path: {sys.path}")
print("=" * 50)

register = template.Library()

@register.filter
def add_months(value, months):
    """
    Agrega N meses a una fecha
    Uso: {{ fecha|add_months:3 }}
    """
    if not value:
        return value
    
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d').date()
        except:
            return value
    
    year = value.year + (value.month + months - 1) // 12
    month = (value.month + months) % 12
    if month == 0:
        month = 12
    
    # Ajustar día si es mayor que los días del mes
    day = value.day
    last_day = calendar.monthrange(year, month)[1]
    if day > last_day:
        day = last_day
    
    return date(year, month, day)

@register.filter
def add_days(value, days):
    """Agrega N días a una fecha"""
    if not value:
        return value
    return value + timedelta(days=days)

@register.filter
def add_weeks(date_obj, weeks):
    """Agrega semanas a una fecha"""
    if not date_obj:
        return None
    try:
        weeks = int(weeks)
        return date_obj + timedelta(weeks=weeks)
    except (ValueError, TypeError):
        return date_obj

@register.filter
def multiply(value, arg):
    """Multiplica un valor por otro"""
    try:
        # Si es Decimal
        if isinstance(value, Decimal):
            return value * Decimal(str(arg))
        # Si es float o int
        elif isinstance(value, (float, int)):
            return float(value) * float(arg)
        # Si es string
        else:
            return Decimal(str(value)) * Decimal(str(arg))
    except (ValueError, TypeError, InvalidOperation):
        try:
            return float(value) * float(arg)
        except:
            return 0

@register.filter
def divide(value, arg):
    """Divide un valor por un número"""
    try:
        # Manejar Decimal
        if isinstance(value, Decimal):
            arg_dec = Decimal(str(arg))
            return value / arg_dec if arg_dec != 0 else Decimal('0')
        # Manejar float/int
        else:
            arg_float = float(arg)
            return float(value) / arg_float if arg_float != 0 else 0
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def calculate_percentage(value, percentage_value):
    """Calcula el porcentaje de un valor"""
    try:
        if isinstance(value, Decimal):
            percentage = Decimal(str(percentage_value))
            return (value * percentage) / Decimal('100')
        else:
            return (float(value) * float(percentage_value)) / 100
    except (ValueError, TypeError):
        return 0

@register.filter
def format_percentage(value, decimales=2):
    """Formatea un número como porcentaje"""
    try:
        value = float(value)
        return f"{value:.{int(decimales)}f}%"
    except (ValueError, TypeError):
        return "0%"

@register.filter
def percentage_of(value, total):
    """Calcula qué porcentaje es value de total"""
    try:
        value_f = float(value)
        total_f = float(total)
        if total_f == 0:
            return 0
        return (value_f / total_f) * 100
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def round_to(value, decimales=2):
    """Redondea un número a n decimales"""
    try:
        value_f = float(value)
        return round(value_f, int(decimales))
    except (ValueError, TypeError):
        return 0

@register.filter
def days_diff(date1, date2=None):
    """Calcula diferencia en días entre dos fechas"""
    try:
        if date2 is None:
            date2 = date.today()
        return (date2 - date1).days
    except:
        return 0

@register.filter
def weeks_remaining(saldo, pago_semanal):
    """Calcula semanas restantes basadas en saldo y pago semanal"""
    try:
        saldo_f = float(saldo)
        pago_semanal_f = float(pago_semanal)
        if pago_semanal_f <= 0:
            return 0
        semanas = saldo_f / pago_semanal_f
        # Redondear hacia arriba
        return int(semanas) if semanas.is_integer() else int(semanas) + 1
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

# Filtro para calcular el total con interés
@register.filter
def total_con_interes(monto, tasa):
    """Calcula monto total con interés"""
    try:
        monto_dec = Decimal(str(monto))
        tasa_dec = Decimal(str(tasa))
        interes = (monto_dec * tasa_dec) / Decimal('100')
        return monto_dec + interes
    except:
        try:
            return float(monto) * (1 + float(tasa) / 100)
        except:
            return monto

# Filtro para formatear como moneda
@register.filter
def currency(value):
    """Formatea un número como moneda"""
    try:
        return f"${float(value):,.2f}"
    except:
        return f"${value}"