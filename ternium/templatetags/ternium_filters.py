# ternium/templatetags/ternium_filters.py

from django import template

register = template.Library()

@register.filter(name='abs')
def abs_filter(value):
    """Devuelve el valor absoluto de un número."""
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value