# ternium/templatetags/columnas_extras.py
"""Filtro para pintar el valor de una columna configurable de la tabla de
remisiones sin escribir una rama por campo en la plantilla.

El formateo vive en ternium/columnas_remisiones.py para que la plantilla
Django y la API del frontend Next.js muestren exactamente lo mismo.
"""
from django import template
from django.core.exceptions import ObjectDoesNotExist

from ternium.columnas_remisiones import formatear

register = template.Library()

VACIO = '-'


@register.filter
def valor_col(obj, accessor):
    """Recorre una ruta de atributos ('origen.nombre') y devuelve el valor ya
    formateado. Cualquier tramo nulo corta y devuelve '-'.
    """
    if not accessor:
        return VACIO

    valor = obj
    for tramo in accessor.split('.'):
        if valor is None:
            return VACIO
        try:
            valor = getattr(valor, tramo)
        except (AttributeError, ObjectDoesNotExist):
            return VACIO
        if callable(valor):
            try:
                valor = valor()
            except Exception:
                return VACIO

    return formatear(valor)
