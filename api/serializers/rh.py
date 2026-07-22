"""
api/serializers/rh.py
Serializers para el módulo RH.
"""
from rest_framework import serializers
from RH.models import (
    Departamento, Puesto, MotivoInactivacion,
    DivisionOperativa, TipoCarga, TipoViaje,
    Empleado, Hijo, Salario, TipoDocumentoOperador,
    DocumentoOperador, HistorialLaboral, Contrato,
    MotivoBaja, BajaEmpleado, Vacacion, HistoricoVacaciones,
    Prestamo, PagoPrestamo, ControlVacante,
    PlantillaContrato, ContratoGenerado,
)


class DepartamentoSerializer(serializers.ModelSerializer):
    total_empleados = serializers.SerializerMethodField()

    class Meta:
        model = Departamento
        fields = '__all__'

    def get_total_empleados(self, obj):
        return obj.empleados.filter(activo=True, eliminado=False).count()


class PuestoSerializer(serializers.ModelSerializer):
    departamento_nombre = serializers.CharField(source='departamento.nombre', read_only=True) if hasattr(Puesto, 'departamento') else None
    total_empleados = serializers.SerializerMethodField()

    class Meta:
        model = Puesto
        fields = '__all__'

    def get_total_empleados(self, obj):
        return obj.empleados.filter(activo=True, eliminado=False).count()


class MotivoInactivacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MotivoInactivacion
        fields = '__all__'


class DivisionOperativaSerializer(serializers.ModelSerializer):
    class Meta:
        model = DivisionOperativa
        fields = '__all__'


class TipoCargaSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoCarga
        fields = '__all__'


class TipoViajeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoViaje
        fields = '__all__'


class HijoSerializer(serializers.ModelSerializer):
    edad = serializers.SerializerMethodField()

    class Meta:
        model = Hijo
        fields = '__all__'

    def get_edad(self, obj):
        try:
            return obj.edad
        except Exception:
            return None


class SalarioSerializer(serializers.ModelSerializer):
    sueldo_mensual = serializers.SerializerMethodField()
    sueldo_semanal = serializers.SerializerMethodField()

    class Meta:
        model = Salario
        fields = '__all__'

    def get_sueldo_mensual(self, obj):
        try:
            return float(obj.sueldo_mensual)
        except Exception:
            return None

    def get_sueldo_semanal(self, obj):
        try:
            return float(obj.sueldo_semanal)
        except Exception:
            return None


class TipoDocumentoOperadorSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoDocumentoOperador
        fields = '__all__'


class DocumentoOperadorSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source='tipo_documento.nombre', read_only=True)
    vencido = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoOperador
        fields = '__all__'

    def get_vencido(self, obj):
        from django.utils import timezone
        if obj.fecha_vencimiento:
            return obj.fecha_vencimiento < timezone.now().date()
        return False


class HistorialLaboralSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistorialLaboral
        fields = '__all__'


class ContratoSerializer(serializers.ModelSerializer):
    duracion_dias = serializers.SerializerMethodField()

    class Meta:
        model = Contrato
        fields = '__all__'

    def get_duracion_dias(self, obj):
        try:
            return obj.duracion
        except Exception:
            return None


# ─── EMPLEADO ────────────────────────────────────────────────────────────────
class EmpleadoListSerializer(serializers.ModelSerializer):
    """Ligero para listados."""
    puesto_nombre = serializers.CharField(source='puesto.nombre', read_only=True)
    departamento_nombre = serializers.CharField(source='departamento.nombre', read_only=True)
    antiguedad_anios = serializers.SerializerMethodField()

    class Meta:
        model = Empleado
        fields = [
            'id', 'numero_empleado', 'nombre', 'apellido', 'nombre_completo',
            'email', 'empresa', 'activo', 'fecha_ingreso',
            'puesto', 'puesto_nombre',
            'departamento', 'departamento_nombre',
            'antiguedad_anios',
        ]

    def get_antiguedad_anios(self, obj):
        try:
            return round(obj.antiguedad, 1)
        except Exception:
            return None


class EmpleadoDetailSerializer(serializers.ModelSerializer):
    """Completo para detalle / crear / editar."""
    puesto_nombre = serializers.CharField(source='puesto.nombre', read_only=True)
    departamento_nombre = serializers.CharField(source='departamento.nombre', read_only=True)
    supervisor_nombre = serializers.CharField(source='supervisor.nombre_completo', read_only=True)
    division_operativa = DivisionOperativaSerializer(many=True, read_only=True)
    tipo_carga = TipoCargaSerializer(many=True, read_only=True)
    tipo_viaje = TipoViajeSerializer(many=True, read_only=True)

    hijos = HijoSerializer(many=True, read_only=True)
    salarios = SalarioSerializer(many=True, read_only=True)
    documentos = DocumentoOperadorSerializer(many=True, read_only=True)
    historial_laboral = HistorialLaboralSerializer(many=True, read_only=True)
    contratos = ContratoSerializer(many=True, read_only=True)

    antiguedad_anios = serializers.SerializerMethodField()
    salario_actual = serializers.SerializerMethodField()

    class Meta:
        model = Empleado
        exclude = ['eliminado', 'fecha_eliminacion', 'motivo_eliminacion', 'eliminado_por']

    def get_antiguedad_anios(self, obj):
        try:
            return round(obj.antiguedad, 1)
        except Exception:
            return None

    def get_salario_actual(self, obj):
        try:
            sal = obj.salario_actual
            if sal:
                return {
                    'sueldo_diario': float(sal.sueldo_diario),
                    'sueldo_semanal': float(sal.sueldo_semanal),
                    'sueldo_mensual': float(sal.sueldo_mensual),
                }
        except Exception:
            pass
        return None


# ─── BAJAS ───────────────────────────────────────────────────────────────────
class MotivoBajaSerializer(serializers.ModelSerializer):
    hijos = serializers.SerializerMethodField()

    class Meta:
        model = MotivoBaja
        fields = '__all__'

    def get_hijos(self, obj):
        return MotivoBajaSerializer(
            obj.submotivos.filter(activo=True), many=True
        ).data


class BajaEmpleadoSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.CharField(source='empleado.nombre_completo', read_only=True)

    class Meta:
        model = BajaEmpleado
        fields = '__all__'


# ─── VACACIONES ──────────────────────────────────────────────────────────────
class VacacionSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.CharField(source='empleado.nombre_completo', read_only=True)
    dias_reales = serializers.SerializerMethodField()

    class Meta:
        model = Vacacion
        fields = '__all__'

    def get_dias_reales(self, obj):
        try:
            return obj.dias_reales
        except Exception:
            return None


class HistoricoVacacionesSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricoVacaciones
        fields = '__all__'


# ─── PRÉSTAMOS ───────────────────────────────────────────────────────────────
class PagoPrestamoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PagoPrestamo
        fields = '__all__'


class PrestamoSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.CharField(source='empleado.nombre_completo', read_only=True)
    pagos = PagoPrestamoSerializer(many=True, read_only=True)
    pago_semanal = serializers.SerializerMethodField()
    porcentaje_avance = serializers.SerializerMethodField()

    class Meta:
        model = Prestamo
        fields = '__all__'

    def get_pago_semanal(self, obj):
        try:
            return float(obj.pago_semanal)
        except Exception:
            return None

    def get_porcentaje_avance(self, obj):
        try:
            if obj.monto_total and obj.monto_total > 0:
                return round(float(obj.monto_pagado / obj.monto_total * 100), 1)
        except Exception:
            pass
        return 0


# ─── CONTROL VACANTES ─────────────────────────────────────────────────────────
class ControlVacanteSerializer(serializers.ModelSerializer):
    puesto_nombre = serializers.CharField(source='puesto.nombre', read_only=True)
    division_nombre = serializers.CharField(source='division.nombre', read_only=True)

    class Meta:
        model = ControlVacante
        fields = '__all__'


class PlantillaContratoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlantillaContrato
        fields = '__all__'
        read_only_fields = ['creado_por', 'creado', 'actualizado']


class ContratoGeneradoSerializer(serializers.ModelSerializer):
    empleado_nombre = serializers.SerializerMethodField()

    class Meta:
        model = ContratoGenerado
        fields = '__all__'
        read_only_fields = ['creado_por', 'creado']

    def get_empleado_nombre(self, obj):
        e = obj.empleado
        return f"{e.nombre} {getattr(e, 'apellido', '') or ''}".strip()
