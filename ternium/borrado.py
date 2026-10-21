"""
Borrado de registros de catálogo (Unidades y Permisionarios): solo el personal staff.

Antes de borrar se revisa qué otros registros lo usan:
- protegen: relaciones PROTECT/RESTRICT (p. ej. viajes de una unidad); mientras existan
  no se puede borrar.
- afectados: los que se quedan sin él (SET_NULL) o pierden su vínculo (CASCADE), p. ej.
  remisiones de la unidad. Se borran solo con confirmación (?confirmar=1).
"""
from django.db.models import PROTECT, RESTRICT

# Nombres más claros que el verbose_name del modelo
NOMBRES = {
    ('cargas_diesel', 'unidad'): ('unidad de diésel', 'unidades de diésel'),
    ('cargas_diesel', 'permisionariounidad'): ('vínculo con permisionario', 'vínculos con permisionario'),
}


def es_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _nombre(modelo, n):
    meta = modelo._meta
    singular, plural = NOMBRES.get((meta.app_label, meta.model_name), (meta.verbose_name, meta.verbose_name_plural))
    return f'{n:,} {str(singular if n == 1 else plural).lower()}'


def uso(obj):
    """{'protegen': [...], 'afectados': [...]} con textos como "12 remisiones"."""
    protegen, afectados = [], []
    for rel in obj._meta.related_objects:
        if rel.many_to_many:  # solo se quitan los vínculos
            continue
        modelo = rel.related_model
        n = modelo._base_manager.filter(**{rel.field.name: obj}).count()
        if n:
            (protegen if rel.on_delete in (PROTECT, RESTRICT) else afectados).append(_nombre(modelo, n))
    return {'protegen': protegen, 'afectados': afectados}


def revisar_borrado(obj, nombre, confirmar):
    """None si se puede borrar; si no, (mensaje, status HTTP)."""
    u = uso(obj)
    if u['protegen']:
        return (f'No se puede eliminar {nombre}: tiene {", ".join(u["protegen"])}. '
                'Dalo de baja o márcalo fuera de servicio.'), 400
    if u['afectados'] and not confirmar:
        return f'Confirma: {", ".join(u["afectados"])} quedarán sin {nombre}.', 409
    return None
