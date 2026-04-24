from django.contrib import admin
from api.models import ConfiguracionSistema


@admin.register(ConfiguracionSistema)
class ConfiguracionSistemaAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Identidad de la empresa', {
            'fields': (
                'empresa_nombre', 'empresa_rfc', 'empresa_logo_url',
                'empresa_slogan', 'empresa_direccion', 'empresa_telefono',
                'empresa_email', 'empresa_sitio_web',
            )
        }),
        ('UI / Branding', {
            'fields': (
                'color_primario', 'color_secundario', 'color_acento', 'color_peligro',
                'fuente_principal', 'tema_oscuro_por_defecto',
                'idioma_por_defecto', 'zona_horaria', 'moneda_por_defecto',
            )
        }),
        ('Módulos habilitados', {
            'fields': (
                'modulo_remisiones', 'modulo_plastico', 'modulo_tarimas',
                'modulo_maquila', 'modulo_trane', 'modulo_medline',
                'modulo_rh', 'modulo_bancos', 'modulo_compras', 'modulo_cxp',
                'modulo_facturacion', 'modulo_diesel', 'modulo_chat', 'modulo_ia',
                'modulo_dashboard_patio', 'modulo_reportes_kpi',
            )
        }),
        ('Reglas de negocio – Remisiones', {
            'fields': (
                'merma_umbral_alerta_default', 'peso_default_unidad_medida',
                'dias_auditoria_limite', 'permitir_remision_sin_boleta',
                'auto_cancelar_remision_dias', 'folio_medline_formato',
            )
        }),
        ('Reglas de negocio – RH', {
            'fields': (
                'rh_dias_vacaciones_primer_anio', 'rh_dias_vacaciones_incremento',
                'rh_prestamo_limite_meses_sueldo', 'rh_prestamo_max_porcentaje_descuento',
                'rh_empresa_choices',
            )
        }),
        ('Reglas de negocio – Diesel', {
            'fields': ('diesel_alerta_minima_litros', 'urea_alerta_minima_litros')
        }),
        ('Reglas de negocio – Compras', {
            'fields': ('compras_aprobacion_requerida', 'compras_monto_aprobacion_automatica')
        }),
        ('Reglas de negocio – CxP / Bancos', {
            'fields': ('cxp_dias_alerta_vencimiento', 'bancos_tc_default')
        }),
        ('Notificaciones', {
            'fields': (
                'notificaciones_email_activas', 'notificaciones_whatsapp_activas',
                'email_alertas_merma', 'email_alertas_cxp',
            )
        }),
        ('API / Integraciones externas', {
            'classes': ('collapse',),
            'fields': (
                'fiscalapi_key', 'fiscalapi_url', 'fiscalapi_modo_produccion',
                'banxico_api_token', 'twilio_activo', 'twilio_whatsapp_from',
            )
        }),
        ('Paginación / Listas', {
            'fields': ('items_por_pagina', 'items_por_pagina_maximo')
        }),
        ('Almacenamiento', {
            'classes': ('collapse',),
            'fields': ('storage_backend', 's3_bucket_nombre', 's3_region')
        }),
        ('Auditoría', {
            'classes': ('collapse',),
            'fields': ('actualizado_en', 'actualizado_por')
        }),
    )
    readonly_fields = ['actualizado_en', 'actualizado_por']

    def has_add_permission(self, request):
        # Solo puede existir 1 registro
        return not ConfiguracionSistema.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
