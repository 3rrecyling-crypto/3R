# Adds permissions for Dashboard TRANE and Dashboard Remisiones modules.

from django.db import migrations


PERMISSIONS = [
    ('can_audit_remision', 'Puede auditar remisiones'),
    ('view_ternium_module', 'Puede acceder al módulo Ternium'),
    ('acceso_ia', 'Acceso a Inteligencia Artificial'),
    ('acceso_remisiones', 'Acceso a Módulo Remisiones'),
    ('acceso_dashboard_patio', 'Acceso a Dashboard Patios'),
    ('acceso_catalogos', 'Acceso a Catálogos'),
    ('acceso_reportes_kpi', 'Acceso a Reportes y KPIs'),
    ('acceso_trane', 'Acceso al Portal Trane'),
    ('acceso_bancos', 'Acceso a Flujo Bancario'),
    ('acceso_dashboard', 'Acceso a Dashboard Principal'),
    ('acceso_diesel', 'Acceso a Control Diésel'),
    # Nuevos
    ('ver_dashboard_trane', 'Puede ver el Dashboard TRANE'),
    ('exportar_dashboard_trane', 'Puede exportar reportes del Dashboard TRANE'),
    ('acceso_dashboard_remisiones', 'Acceso al Dashboard de Remisiones'),
    ('ver_kpis_remisiones', 'Puede ver KPIs y métricas de remisiones'),
    ('exportar_remisiones', 'Puede exportar reportes de remisiones a Excel'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('ternium', '0079_destinatarioalertamerma'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='remision',
            options={
                'ordering': ['-fecha', '-creado_en'],
                'permissions': PERMISSIONS,
                'verbose_name': 'Remisión',
                'verbose_name_plural': 'Remisiones',
            },
        ),
    ]
