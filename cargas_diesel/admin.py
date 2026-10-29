from decimal import Decimal

from django.contrib import admin
from django.db import transaction

from .models import (
    Patio, PerfilUsuarioDiesel, ProveedorDiesel, Unidad,
    Totem, CompraCombustible, AjusteInventario, CargaDiesel,
    Permisionario, PermisionarioUnidad, Thermo,
)


def _cambio(antes, obj, *campos):
    """¿Es alta (no hay antes) o cambió alguno de esos campos?"""
    return antes is None or any(getattr(antes, c) != getattr(obj, c) for c in campos)


@transaction.atomic
def _mover_totems(movimientos):
    """Suma a cada tótem los litros de {(patio_id, 'diesel' | 'urea'): litros} (negativo = salen),
    sin pasar de su capacidad ni bajar de 0, como las compras y los ajustes."""
    for (patio_id, combustible), litros in movimientos.items():
        if not litros:
            continue
        totem = Totem.objects.select_for_update().filter(patio_id=patio_id).first()
        if totem:
            campo = f'cantidad_{combustible}'
            nivel = min(max(getattr(totem, campo) + litros, Decimal('0')), getattr(totem, f'capacidad_{combustible}'))
            setattr(totem, campo, nivel)
            totem.save()


class CorrigeTotemAdmin(admin.ModelAdmin):
    """Editar o borrar desde el admin una carga, compra o ajuste se refleja en Control Diésel: se
    deshace lo que el registro había movido en el tótem y se aplica lo que mueve ahora (al darlos
    de alta, eso ya lo hace su save())."""

    def movimiento(self, obj):
        """{(patio_id, combustible): litros} que el registro metió (+) o sacó (-) del tótem."""
        raise NotImplementedError

    def antes_de_guardar(self, obj, antes):
        pass

    def despues_de_guardar(self, obj, antes):
        pass

    def despues_de_borrar(self, obj):
        pass

    def _corregir_totem(self, antes, despues):
        suma = {}
        for obj, signo in ((antes, -1), (despues, 1)):
            if obj is not None:
                for clave, litros in self.movimiento(obj).items():
                    suma[clave] = suma.get(clave, Decimal('0')) + signo * litros
        _mover_totems(suma)

    def save_model(self, request, obj, form, change):
        antes = type(obj).objects.get(pk=obj.pk) if change else None
        self.antes_de_guardar(obj, antes)
        super().save_model(request, obj, form, change)
        if antes:
            self._corregir_totem(antes, obj)
        self.despues_de_guardar(obj, antes)

    def delete_model(self, request, obj):
        self._corregir_totem(obj, None)
        super().delete_model(request, obj)
        self.despues_de_borrar(obj)

    def delete_queryset(self, request, queryset):
        # "Eliminar seleccionados": uno por uno para que cada uno corrija el tótem.
        with transaction.atomic():
            for obj in queryset:
                self.delete_model(request, obj)


def _recalcular_costos(patio_id, desde):
    """Las cargas del patio que tomaron su precio por litro de la compra de esa fecha (hasta la
    siguiente compra de diésel) vuelven a sacar su precio y su costo. Las importadas del control
    anterior van sin costo y así se quedan."""
    cargas = CargaDiesel.objects.filter(patio_id=patio_id, fecha_carga__gte=desde, precio_litro__gt=0)
    siguiente = CompraCombustible.objects.filter(patio_id=patio_id, tipo='diesel', fecha__gt=desde).order_by('fecha').first()
    if siguiente:
        cargas = cargas.filter(fecha_carga__lt=siguiente.fecha)
    for c in cargas:
        precio, costo = c.precio_litro, c.costo_total
        c.calcular_costo()
        if (c.precio_litro, c.costo_total) != (precio, costo):
            CargaDiesel.objects.filter(pk=c.pk).update(precio_litro=c.precio_litro, costo_total=c.costo_total)


@admin.register(Patio)
class PatioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'codigo', 'activo', 'created_at']
    list_filter = ['activo']
    search_fields = ['nombre', 'codigo']


@admin.register(PerfilUsuarioDiesel)
class PerfilUsuarioDieselAdmin(admin.ModelAdmin):
    list_display = ['user', 'es_global']
    list_filter = ['es_global']
    filter_horizontal = ['patios']


@admin.register(ProveedorDiesel)
class ProveedorDieselAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'rfc', 'contacto', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre', 'rfc']


class PermisionarioUnidadInline(admin.TabularInline):
    model = PermisionarioUnidad
    extra = 0
    autocomplete_fields = ['unidad']


@admin.register(Permisionario)
class PermisionarioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'rfc', 'telefono', 'correo', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre', 'rfc', 'correo']
    inlines = [PermisionarioUnidadInline]


@admin.register(Thermo)
class ThermoAdmin(admin.ModelAdmin):
    list_display = ['identificador', 'descripcion', 'numero_serie', 'permisionario', 'activo']
    list_filter = ['activo', 'permisionario']
    search_fields = ['identificador', 'descripcion', 'numero_serie']


@admin.register(Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display = ['numero_economico', 'descripcion', 'tipo', 'patio', 'activo']
    list_filter = ['activo', 'patio']
    search_fields = ['numero_economico', 'descripcion']


@admin.register(Totem)
class TotemAdmin(admin.ModelAdmin):
    list_display = [
        'nombre', 'patio', 'cantidad_diesel', 'capacidad_diesel',
        'cantidad_urea', 'capacidad_urea', 'updated_at'
    ]
    list_filter = ['patio']
    readonly_fields = ['updated_at']


@admin.register(CompraCombustible)
class CompraCombustibleAdmin(CorrigeTotemAdmin):
    list_display = [
        'fecha', 'patio', 'tipo', 'proveedor', 'litros',
        'precio_unitario', 'total', 'numero_factura', 'usuario'
    ]
    list_filter = ['tipo', 'patio', 'proveedor']
    search_fields = ['numero_factura', 'proveedor_nombre']
    date_hierarchy = 'fecha'
    readonly_fields = ['total', 'proveedor_nombre']

    def movimiento(self, c):
        return {(c.patio_id, c.tipo): c.litros}

    def despues_de_guardar(self, c, antes):
        # El precio de las cargas sale de la última compra de diésel a su fecha.
        if antes and _cambio(antes, c, 'precio_unitario', 'patio_id', 'tipo'):
            _recalcular_costos(antes.patio_id, antes.fecha)
            _recalcular_costos(c.patio_id, c.fecha)

    def despues_de_borrar(self, c):
        _recalcular_costos(c.patio_id, c.fecha)


@admin.register(AjusteInventario)
class AjusteInventarioAdmin(CorrigeTotemAdmin):
    list_display = [
        'fecha', 'patio', 'tipo_combustible', 'tipo_movimiento',
        'litros', 'cantidad_anterior', 'cantidad_posterior', 'motivo', 'usuario'
    ]
    list_filter = ['tipo_combustible', 'tipo_movimiento', 'patio']
    date_hierarchy = 'fecha'
    readonly_fields = ['cantidad_anterior', 'cantidad_posterior']

    def movimiento(self, a):
        return {(a.patio_id, a.tipo_combustible): a.litros if a.tipo_movimiento == 'entrada' else -a.litros}


@admin.register(CargaDiesel)
class CargaDieselAdmin(CorrigeTotemAdmin):
    """Lo que el sistema calcula al registrar la carga se vuelve a calcular al editarla aquí:
    nombre del permisionario, rendimiento (el suyo y el de la siguiente carga de la unidad),
    costo y tótem."""
    list_display = [
        'fecha_carga', 'patio', 'unidad', 'thermo', 'tipo_carga', 'odometro',
        'litros_diesel', 'litros_thermo', 'litros_urea',
        'costo_total', 'rendimiento', 'permisionario_nombre', 'usuario'
    ]
    list_filter = ['patio', 'tipo_carga', 'unidad']
    search_fields = ['unidad__numero_economico']
    date_hierarchy = 'fecha_carga'
    readonly_fields = ['rendimiento', 'costo_total', 'precio_litro']

    def movimiento(self, c):
        # Las importadas del control anterior no descontaron del tótem (no tienen "tótem después").
        if c.totem_despues is None:
            return {}
        return {(c.patio_id, 'diesel'): -(c.litros_diesel + c.litros_thermo), (c.patio_id, 'urea'): -c.litros_urea}

    def antes_de_guardar(self, c, antes):
        if _cambio(antes, c, 'permisionario_id'):
            c.permisionario_nombre = c.permisionario.nombre if c.permisionario_id else ''
        if _cambio(antes, c, 'unidad_id', 'tipo_carga', 'odometro', 'litros_diesel'):
            c.rendimiento = c.calcular_rendimiento()
        # Las importadas van sin costo y así se quedan.
        if antes is None or (c.precio_litro and _cambio(antes, c, 'patio_id', 'litros_diesel', 'litros_thermo')):
            c.calcular_costo()

    def despues_de_guardar(self, c, antes):
        if antes is None:
            c.descontar_del_totem()  # alta desde el admin: igual que desde el sistema
        elif _cambio(antes, c, 'unidad_id', 'tipo_carga', 'odometro'):
            antes.recalcular_siguiente()  # la que seguía con los datos de antes
            c.recalcular_siguiente()

    def despues_de_borrar(self, c):
        c.recalcular_siguiente()
