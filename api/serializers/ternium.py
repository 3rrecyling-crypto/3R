"""
api/serializers/ternium.py
Serializers para todos los modelos del app ternium.
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from ternium.models import (
    Origen, Empresa, LineaTransporte, Operador, Material, Unidad,
    Contenedor, Lugar, Cliente, Remision, DetalleRemision,
    RegistroLogistico, EntradaMaquila, EvidenciaRemision,
    HistorialRemision, InventarioPatio, Descarga, Plastico,
    EvidenciaPlastico, HistorialPlastico, ControlTarima,
    ConfiguracionManifiesto, ControlManifiestoTrane,
    PrecioMedline, ConfiguracionAlertaMerma, DestinatarioAlertaMerma,
    Profile,
)


# ─── AUTH / USERS ────────────────────────────────────────────────────────────
class UserMiniSerializer(serializers.ModelSerializer):
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'nombre_completo']

    def get_nombre_completo(self, obj):
        return obj.get_full_name() or obj.username


class ProfileSerializer(serializers.ModelSerializer):
    user = UserMiniSerializer(read_only=True)
    empresas_autorizadas = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    permisos = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = '__all__'

    def get_permisos(self, obj):
        user = obj.user
        perms = [
            'acceso_remisiones', 'acceso_catalogos', 'acceso_reportes_kpi',
            'acceso_trane', 'acceso_bancos', 'acceso_dashboard',
            'acceso_diesel', 'acceso_dashboard_patio', 'acceso_ia',
            'can_audit_remision', 'view_ternium_module',
        ]
        result = {}
        for perm in perms:
            result[perm] = (
                user.has_perm(f'ternium.{perm}') or
                user.has_perm(f'flujo_bancos.{perm}') or
                user.is_superuser
            )
        result['is_superuser'] = user.is_superuser
        result['is_staff'] = user.is_staff
        return result


# ─── CATÁLOGOS ────────────────────────────────────────────────────────────────
class OrigenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Origen
        fields = '__all__'


class EmpresaSerializer(serializers.ModelSerializer):
    origenes = OrigenSerializer(many=True, read_only=True)
    origenes_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Origen.objects.all(), source='origenes', write_only=True
    )

    class Meta:
        model = Empresa
        fields = '__all__'


class EmpresaMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Empresa
        fields = ['id', 'nombre', 'prefijo']


class LineaTransporteSerializer(serializers.ModelSerializer):
    empresas = EmpresaMiniSerializer(many=True, read_only=True)
    empresas_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Empresa.objects.all(), source='empresas', write_only=True
    )

    class Meta:
        model = LineaTransporte
        fields = '__all__'


class OperadorSerializer(serializers.ModelSerializer):
    empresas = EmpresaMiniSerializer(many=True, read_only=True)
    empresas_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Empresa.objects.all(), source='empresas', write_only=True
    )

    class Meta:
        model = Operador
        fields = '__all__'


class MaterialSerializer(serializers.ModelSerializer):
    empresas = EmpresaMiniSerializer(many=True, read_only=True)
    empresas_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Empresa.objects.all(), source='empresas', write_only=True
    )

    class Meta:
        model = Material
        fields = '__all__'


class UnidadSerializer(serializers.ModelSerializer):
    empresas = EmpresaMiniSerializer(many=True, read_only=True)
    empresas_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Empresa.objects.all(), source='empresas', write_only=True
    )

    class Meta:
        model = Unidad
        fields = '__all__'


class ContenedorSerializer(serializers.ModelSerializer):
    empresas = EmpresaMiniSerializer(many=True, read_only=True)
    empresas_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Empresa.objects.all(), source='empresas', write_only=True
    )

    class Meta:
        model = Contenedor
        fields = '__all__'


class LugarSerializer(serializers.ModelSerializer):
    empresas = EmpresaMiniSerializer(many=True, read_only=True)
    empresas_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Empresa.objects.all(), source='empresas', write_only=True
    )

    class Meta:
        model = Lugar
        fields = '__all__'


class LugarMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lugar
        fields = ['id', 'nombre', 'tipo', 'es_patio']


class ClienteSerializer(serializers.ModelSerializer):
    empresas = EmpresaMiniSerializer(many=True, read_only=True)
    empresas_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Empresa.objects.all(), source='empresas', write_only=True
    )

    class Meta:
        model = Cliente
        fields = '__all__'


# ─── REMISIONES ───────────────────────────────────────────────────────────────
class DetalleRemisionSerializer(serializers.ModelSerializer):
    material_nombre = serializers.CharField(source='material.nombre', read_only=True)

    class Meta:
        model = DetalleRemision
        fields = '__all__'


class EvidenciaRemisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenciaRemision
        fields = '__all__'


class HistorialRemisionSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source='usuario.get_full_name', read_only=True)

    class Meta:
        model = HistorialRemision
        fields = '__all__'


class RemisionListSerializer(serializers.ModelSerializer):
    """Serializer ligero para listados paginados."""
    empresa_nombre = serializers.CharField(source='empresa.nombre', read_only=True)
    operador_nombre = serializers.CharField(source='operador.nombre', read_only=True)
    origen_nombre = serializers.CharField(source='origen.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='destino.nombre', read_only=True)
    porcentaje_merma = serializers.SerializerMethodField()

    class Meta:
        model = Remision
        fields = [
            'id', 'remision', 'folio', 'fecha', 'status',
            'empresa', 'empresa_nombre',
            'operador', 'operador_nombre',
            'origen', 'origen_nombre',
            'destino', 'destino_nombre',
            'folio_medline', 'folio_ld', 'folio_dlv',
            'porcentaje_merma',
        ]

    def get_porcentaje_merma(self, obj):
        try:
            return float(obj.porcentaje_merma)
        except Exception:
            return None


class RemisionDetailSerializer(serializers.ModelSerializer):
    """Serializer completo para detalle / creación / edición."""
    empresa_nombre = serializers.CharField(source='empresa.nombre', read_only=True)
    operador_nombre = serializers.CharField(source='operador.nombre', read_only=True)
    linea_transporte_nombre = serializers.CharField(source='linea_transporte.nombre', read_only=True)
    unidad_placas = serializers.CharField(source='unidad.license_plate', read_only=True)
    contenedor_nombre = serializers.CharField(source='contenedor.nombre', read_only=True)
    origen_nombre = serializers.CharField(source='origen.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='destino.nombre', read_only=True)
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)

    detalles = DetalleRemisionSerializer(many=True, read_only=True)
    evidencias = EvidenciaRemisionSerializer(many=True, read_only=True)
    historial = HistorialRemisionSerializer(many=True, read_only=True)

    porcentaje_merma = serializers.SerializerMethodField()
    permite_manifiesto_destruccion = serializers.SerializerMethodField()
    destruccion_fiscal_completa = serializers.SerializerMethodField()

    class Meta:
        model = Remision
        fields = '__all__'

    def get_porcentaje_merma(self, obj):
        try:
            return float(obj.porcentaje_merma)
        except Exception:
            return None

    def get_permite_manifiesto_destruccion(self, obj):
        try:
            return obj.permite_manifiesto_destruccion
        except Exception:
            return False

    def get_destruccion_fiscal_completa(self, obj):
        try:
            return obj.destruccion_fiscal_completa
        except Exception:
            return False


# ─── REGISTRO LOGÍSTICO ──────────────────────────────────────────────────────
class RegistroLogisticoSerializer(serializers.ModelSerializer):
    remision_folio = serializers.CharField(source='remision.remision', read_only=True)
    merma_absoluta = serializers.SerializerMethodField()

    class Meta:
        model = RegistroLogistico
        fields = '__all__'

    def get_merma_absoluta(self, obj):
        try:
            return float(obj.merma_absoluta)
        except Exception:
            return None


# ─── ENTRADA MAQUILA ─────────────────────────────────────────────────────────
class EntradaMaquilaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntradaMaquila
        fields = '__all__'


# ─── INVENTARIO ──────────────────────────────────────────────────────────────
class InventarioPatiSerializer(serializers.ModelSerializer):
    patio_nombre = serializers.CharField(source='patio.nombre', read_only=True)
    material_nombre = serializers.CharField(source='material.nombre', read_only=True)
    cantidad_ton = serializers.SerializerMethodField()

    class Meta:
        model = InventarioPatio
        fields = '__all__'

    def get_cantidad_ton(self, obj):
        try:
            return float(obj.cantidad / 1000)
        except Exception:
            return None


class DescargaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Descarga
        fields = '__all__'


# ─── PLÁSTICO ────────────────────────────────────────────────────────────────
class EvidenciaPlasticoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvidenciaPlastico
        fields = '__all__'


class HistorialPlasticoSerializer(serializers.ModelSerializer):
    usuario_nombre = serializers.CharField(source='usuario.get_full_name', read_only=True)

    class Meta:
        model = HistorialPlastico
        fields = '__all__'


class PlasticoSerializer(serializers.ModelSerializer):
    empresa_nombre = serializers.CharField(source='empresa.nombre', read_only=True)
    origen_nombre = serializers.CharField(source='origen.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='destino.nombre', read_only=True)
    operador_nombre = serializers.CharField(source='operador.nombre', read_only=True)
    peso_neto = serializers.SerializerMethodField()
    venta_total = serializers.SerializerMethodField()
    evidencias = EvidenciaPlasticoSerializer(many=True, read_only=True)
    historial = HistorialPlasticoSerializer(many=True, read_only=True)

    class Meta:
        model = Plastico
        fields = '__all__'

    def get_peso_neto(self, obj):
        try:
            return float(obj.peso_neto)
        except Exception:
            return None

    def get_venta_total(self, obj):
        try:
            return float(obj.venta_total)
        except Exception:
            return None


# ─── CONTROL TARIMAS ─────────────────────────────────────────────────────────
class ControlTarimaSerializer(serializers.ModelSerializer):
    origen_nombre = serializers.CharField(source='origen.nombre', read_only=True)
    destino_nombre = serializers.CharField(source='destino.nombre', read_only=True)
    total_general = serializers.SerializerMethodField()

    class Meta:
        model = ControlTarima
        fields = '__all__'

    def get_total_general(self, obj):
        try:
            return float(obj.total_general)
        except Exception:
            return None


# ─── MANIFIESTOS / TRANE ─────────────────────────────────────────────────────
class ConfiguracionManifiestoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConfiguracionManifiesto
        fields = '__all__'


class ControlManifiestoTraneSerializer(serializers.ModelSerializer):
    class Meta:
        model = ControlManifiestoTrane
        fields = '__all__'


# ─── MEDLINE ─────────────────────────────────────────────────────────────────
class PrecioMedlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrecioMedline
        fields = '__all__'


# ─── ALERTAS MERMA ───────────────────────────────────────────────────────────
class ConfiguracionAlertaMermaSerializer(serializers.ModelSerializer):
    material_nombre = serializers.CharField(source='material.nombre', read_only=True)

    class Meta:
        model = ConfiguracionAlertaMerma
        fields = '__all__'


class DestinatarioAlertaMermaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DestinatarioAlertaMerma
        fields = '__all__'
