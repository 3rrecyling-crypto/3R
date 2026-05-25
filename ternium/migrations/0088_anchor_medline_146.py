"""
Data migration: ancla el folio Medline de la remisión NLD-611 al valor
`3R-2026-05-146`. A partir de ese punto el contador global (max+1) tomará
147, 148, 149... independientemente del año/mes en curso (el prefijo del
folio sí refleja el año y mes de cada remisión).

Si NLD-611 no existe, la migración es no-op y no falla. Si ya tiene
`3R-2026-05-146` u otro folio Medline, se respeta y solo se aplica la
fuerza si no estaba en 146.
"""
from django.db import migrations


REMISION_OBJETIVO = "NLD-611"
FOLIO_OBJETIVO = "3R-2026-05-146"


def anclar_146(apps, schema_editor):
    Remision = apps.get_model("ternium", "Remision")
    qs = Remision.objects.filter(remision=REMISION_OBJETIVO)
    if not qs.exists():
        return  # no-op si no está la remisión

    # Si ya existe alguna OTRA remisión con `3R-2026-05-146`, no la
    # sobrescribimos — solo registramos un aviso (silencioso, no rompe).
    conflicto = Remision.objects.filter(folio_medline=FOLIO_OBJETIVO).exclude(remision=REMISION_OBJETIVO)
    if conflicto.exists():
        return

    for r in qs:
        if r.folio_medline != FOLIO_OBJETIVO:
            r.folio_medline = FOLIO_OBJETIVO
            r.save(update_fields=["folio_medline"])


def revertir(apps, schema_editor):
    # No-op: una vez asignado, el folio es histórico — no se revierte
    # automáticamente.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0087_remisionalertamermalog'),
    ]

    operations = [
        migrations.RunPython(anclar_146, revertir),
    ]
