"""
api/models.py
─────────────────────────────────────────────────────────────
Modelo de Configuración del Sistema.
Centraliza TODOS los parámetros que el frontend Next.js / React
puede leer vía GET /api/v1/config/ y modificar vía PATCH /api/v1/config/
si el usuario tiene permisos de administrador.
─────────────────────────────────────────────────────────────
"""
from django.db import models
from django.contrib.auth.models import User


# ─── SINGLETON HELPER ────────────────────────────────────────────────────────
class SingletonModel(models.Model):
    """Solo puede existir un registro. Úsalo vía ConfiguracionSistema.get_config()."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # no se puede borrar

    @classmethod
    def get_config(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


# ─── CONFIGURACIÓN GLOBAL ────────────────────────────────────────────────────
class ConfiguracionSistema(SingletonModel):
    """
    CONFIGURACIÓN MAESTRA DEL SISTEMA
    Todos los valores que el frontend puede leer / editar.
    """

    # ── Identidad ────────────────────────────────────────────────────────────
    empresa_nombre = models.CharField(
        max_length=200, default='3R Recycling',
        verbose_name='Nombre de la empresa'
    )
    empresa_rfc = models.CharField(
        max_length=13, blank=True, default='',
        verbose_name='RFC de la empresa'
    )
    empresa_logo_url = models.URLField(
        blank=True, default='',
        verbose_name='URL del logotipo'
    )
    empresa_slogan = models.CharField(
        max_length=300, blank=True, default='',
        verbose_name='Slogan'
    )
    empresa_direccion = models.TextField(
        blank=True, default='',
        verbose_name='Dirección física'
    )
    empresa_telefono = models.CharField(
        max_length=20, blank=True, default='',
        verbose_name='Teléfono principal'
    )
    empresa_email = models.EmailField(
        blank=True, default='',
        verbose_name='Email principal'
    )
    empresa_sitio_web = models.URLField(
        blank=True, default='',
        verbose_name='Sitio web'
    )

    # ── UI / Branding ─────────────────────────────────────────────────────────
    color_primario = models.CharField(
        max_length=7, default='#1a73e8',
        help_text='Hex CSS: #RRGGBB',
        verbose_name='Color primario'
    )
    color_secundario = models.CharField(
        max_length=7, default='#34a853',
        help_text='Hex CSS: #RRGGBB',
        verbose_name='Color secundario'
    )
    color_acento = models.CharField(
        max_length=7, default='#fbbc05',
        verbose_name='Color de acento'
    )
    color_peligro = models.CharField(
        max_length=7, default='#ea4335',
        verbose_name='Color de peligro / error'
    )
    fuente_principal = models.CharField(
        max_length=100, default='Inter, sans-serif',
        verbose_name='Fuente principal'
    )
    tema_oscuro_por_defecto = models.BooleanField(
        default=False,
        verbose_name='Tema oscuro por defecto'
    )
    idioma_por_defecto = models.CharField(
        max_length=10, default='es',
        verbose_name='Idioma por defecto (es/en)'
    )
    zona_horaria = models.CharField(
        max_length=50, default='America/Monterrey',
        verbose_name='Zona horaria'
    )
    moneda_por_defecto = models.CharField(
        max_length=3, default='MXN',
        verbose_name='Moneda por defecto (MXN/USD)'
    )

    # ── Módulos habilitados ──────────────────────────────────────────────────
    modulo_remisiones = models.BooleanField(default=True, verbose_name='Módulo Remisiones')
    modulo_plastico = models.BooleanField(default=True, verbose_name='Módulo Plástico')
    modulo_tarimas = models.BooleanField(default=True, verbose_name='Módulo Control Tarimas')
    modulo_maquila = models.BooleanField(default=True, verbose_name='Módulo Maquila')
    modulo_trane = models.BooleanField(default=True, verbose_name='Módulo TRANE')
    modulo_medline = models.BooleanField(default=True, verbose_name='Módulo Medline')
    modulo_rh = models.BooleanField(default=True, verbose_name='Módulo RH')
    modulo_bancos = models.BooleanField(default=True, verbose_name='Módulo Bancos')
    modulo_compras = models.BooleanField(default=True, verbose_name='Módulo Compras')
    modulo_cxp = models.BooleanField(default=True, verbose_name='Módulo CxP')
    modulo_facturacion = models.BooleanField(default=True, verbose_name='Módulo Facturación')
    modulo_diesel = models.BooleanField(default=True, verbose_name='Módulo Diesel')
    modulo_chat = models.BooleanField(default=True, verbose_name='Módulo Chat')
    modulo_ia = models.BooleanField(default=False, verbose_name='Módulo IA')
    modulo_dashboard_patio = models.BooleanField(default=True, verbose_name='Dashboard Patio')
    modulo_reportes_kpi = models.BooleanField(default=True, verbose_name='Reportes y KPIs')

    # ── Reglas de negocio – Remisiones ───────────────────────────────────────
    merma_umbral_alerta_default = models.DecimalField(
        max_digits=5, decimal_places=2, default=5.00,
        verbose_name='% Merma umbral de alerta (default)'
    )
    peso_default_unidad_medida = models.CharField(
        max_length=3, default='TON',
        choices=[('TON', 'Toneladas'), ('KG', 'Kilogramos')],
        verbose_name='Unidad de peso por defecto'
    )
    dias_auditoria_limite = models.PositiveIntegerField(
        default=30,
        verbose_name='Días límite para auditar remisión'
    )
    permitir_remision_sin_boleta = models.BooleanField(
        default=True,
        verbose_name='Permitir remisión sin boleta de báscula'
    )
    auto_cancelar_remision_dias = models.PositiveIntegerField(
        default=0,
        help_text='0 = nunca cancelar automáticamente',
        verbose_name='Días para auto-cancelar remisión inactiva'
    )
    folio_medline_formato = models.CharField(
        max_length=20, default='3R-{YYYY}-{MM}-{NNN}',
        verbose_name='Formato folio Medline'
    )

    # ── Reglas de negocio – RH ───────────────────────────────────────────────
    rh_dias_vacaciones_primer_anio = models.PositiveIntegerField(
        default=12,
        verbose_name='Días vacaciones 1er año'
    )
    rh_dias_vacaciones_incremento = models.PositiveIntegerField(
        default=2,
        verbose_name='Días extras por año adicional'
    )
    rh_prestamo_limite_meses_sueldo = models.PositiveIntegerField(
        default=3,
        verbose_name='Límite préstamo (# sueldos mensuales)'
    )
    rh_prestamo_max_porcentaje_descuento = models.DecimalField(
        max_digits=5, decimal_places=2, default=40.00,
        verbose_name='% máximo de descuento semanal para préstamos'
    )
    rh_empresa_choices = models.JSONField(
        default=list,
        blank=True,
        help_text='Lista de empresas para el módulo RH. Ej: ["MIGMAR","MARCO_MORALES"]',
        verbose_name='Empresas RH disponibles'
    )

    # ── Reglas de negocio – Diesel ───────────────────────────────────────────
    diesel_alerta_minima_litros = models.DecimalField(
        max_digits=10, decimal_places=2, default=500.00,
        verbose_name='Litros mínimos antes de alerta diesel'
    )
    urea_alerta_minima_litros = models.DecimalField(
        max_digits=10, decimal_places=2, default=200.00,
        verbose_name='Litros mínimos antes de alerta urea'
    )

    # ── Reglas de negocio – Compras ──────────────────────────────────────────
    compras_aprobacion_requerida = models.BooleanField(
        default=True,
        verbose_name='Solicitudes de compra requieren aprobación'
    )
    compras_monto_aprobacion_automatica = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Montos menores a este valor se aprueban automáticamente. 0 = desactivado',
        verbose_name='Monto auto-aprobación compras'
    )

    # ── Reglas de negocio – CxP / Bancos ─────────────────────────────────────
    cxp_dias_alerta_vencimiento = models.PositiveIntegerField(
        default=7,
        verbose_name='Días antes del vencimiento para alertar CxP'
    )
    bancos_tc_default = models.DecimalField(
        max_digits=10, decimal_places=4, default=17.0000,
        verbose_name='Tipo de cambio USD/MXN por defecto'
    )

    # ── Notificaciones ───────────────────────────────────────────────────────
    notificaciones_email_activas = models.BooleanField(
        default=True,
        verbose_name='Notificaciones por email activas'
    )
    notificaciones_whatsapp_activas = models.BooleanField(
        default=False,
        verbose_name='Notificaciones WhatsApp activas'
    )
    email_alertas_merma = models.TextField(
        blank=True, default='',
        help_text='Emails separados por coma para alertas de merma',
        verbose_name='Emails alertas merma'
    )
    email_alertas_cxp = models.TextField(
        blank=True, default='',
        help_text='Emails separados por coma para alertas CxP',
        verbose_name='Emails alertas CxP'
    )

    # ── API / Integraciones externas ─────────────────────────────────────────
    fiscalapi_key = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name='FiscalAPI Key (timbrado CFDI)'
    )
    fiscalapi_url = models.URLField(
        blank=True, default='https://test.fiscalapi.com/api/v4',
        verbose_name='FiscalAPI URL'
    )
    fiscalapi_modo_produccion = models.BooleanField(
        default=False,
        verbose_name='FiscalAPI en producción'
    )
    banxico_api_token = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name='Banxico API Token (tipo de cambio)'
    )
    twilio_activo = models.BooleanField(
        default=False,
        verbose_name='Twilio WhatsApp activo'
    )
    twilio_whatsapp_from = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name='Número WhatsApp emisor Twilio'
    )

    # ── IA (Canvas / Diagramas / Modelador 3D · informes con Claude/DeepSeek) ──
    ia_proveedor = models.CharField(
        max_length=20,
        choices=[('anthropic', 'Anthropic (Claude)'), ('deepseek', 'DeepSeek')],
        default='anthropic',
        verbose_name='Proveedor de IA',
        help_text='Proveedor de IA para asistentes e informes'
    )
    ia_base_url = models.URLField(
        blank=True, default='',
        verbose_name='URL base del proveedor de IA',
        help_text='Vacío = default. DeepSeek: https://api.deepseek.com'
    )
    ia_api_key = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='API Key de IA (texto)',
        help_text='API key del proveedor (Anthropic o DeepSeek)'
    )
    ia_modelo = models.CharField(
        max_length=60, blank=True, default='',
        verbose_name='Modelo de IA',
        help_text='Vacío = el por defecto del proveedor'
    )
    imagen_api_key = models.CharField(
        max_length=255, blank=True, default='',
        verbose_name='API Key de Google Gemini (imágenes)',
        help_text='Para generar imágenes en Canvas (aistudio.google.com/apikey)'
    )
    imagen_modelo = models.CharField(
        max_length=80, blank=True, default='',
        verbose_name='Modelo de imagen de Gemini',
        help_text='Vacío = el por defecto'
    )

    # ── Paginación / Listas ───────────────────────────────────────────────────
    items_por_pagina = models.PositiveIntegerField(
        default=25,
        verbose_name='Items por página (API y listas)'
    )
    items_por_pagina_maximo = models.PositiveIntegerField(
        default=200,
        verbose_name='Máximo items por página permitido'
    )

    # ── Almacenamiento ────────────────────────────────────────────────────────
    storage_backend = models.CharField(
        max_length=20,
        default='s3',
        choices=[('s3', 'AWS S3'), ('local', 'Sistema de archivos local')],
        verbose_name='Backend de almacenamiento'
    )
    s3_bucket_nombre = models.CharField(
        max_length=100, blank=True, default='3rrecycling',
        verbose_name='Nombre del bucket S3'
    )
    s3_region = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name='Región S3'
    )

    # ── Meta ──────────────────────────────────────────────────────────────────
    actualizado_en = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        verbose_name='Último usuario que modificó la configuración'
    )

    class Meta:
        verbose_name = 'Configuración del Sistema'
        verbose_name_plural = 'Configuración del Sistema'
        permissions = [
            ('can_edit_config', 'Puede editar la configuración del sistema'),
        ]

    def __str__(self):
        return f'Configuración – {self.empresa_nombre}'
