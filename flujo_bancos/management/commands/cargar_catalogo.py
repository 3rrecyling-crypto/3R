from django.core.management.base import BaseCommand
from flujo_bancos.models import Categoria, SubCategoria, UnidadNegocio, Operacion, Cuenta

class Command(BaseCommand):
    help = 'Carga las cuentas y el catálogo inicial del proyecto'

    def handle(self, *args, **kwargs):
        self.stdout.write("Iniciando carga de datos...")

        # 1. Definir Cuentas y Monedas
        cuentas_data = [
            ('BBVA 15171', 'MXN'),
            ('BBVA 58485', 'MXN'),
            ('BBVA 21214', 'MXN'),
            ('FONDOS DE INVERSION', 'MXN'),
            ('TARJETA DE NEGOCIOS', 'MXN'),
            ('BBVA USD', 'USD'),
            ('BANORTE PESOS', 'MXN'),
            ('BANORTE USD', 'USD'),
            ('CONFIRMING', 'MXN'),
            ('IBC BANK', 'USD')
        ]
        
        for nombre, moneda in cuentas_data:
            obj, created = Cuenta.objects.get_or_create(nombre=nombre, defaults={'moneda': moneda})
            if created:
                self.stdout.write(f"Cuenta creada: {nombre} ({moneda})")

        # 2. Unidades de Negocio
        unidades = ['RECICLAJE', 'TRANSPORTE', 'SERVICIO INTEGRAL', 'INTERNO', 'ADMINISTRACION', 'SOCIO']
        for u in unidades: UnidadNegocio.objects.get_or_create(nombre=u)

        # 3. Catálogo de Categorías y Subcategorías (Extraído de tus archivos)
        catalogo = {
            'GASTOS_DE_ADMINISTRACION': [
                'AGUA', 'ARTICULOS DE OFICINA', 'CELULAR', 'INTERNET', 'LUZ', 'NOMINA', 
                'PRESTAMO', 'RENTA', 'SEGUROS', 'VARIOS', 'EQUIPO DE COMPUTO', 
                'GASTOS MARCELO', 'UTILIDAD DEL SOCIO', 'SERVICIOS CONTABLES'
            ],
            'GASTOS_FINANCIEROS': [
                'IVA COMISION', 'SERVICIO BANCO EN LINEA', 'COBRO DE PRESTAMO', 
                'PAGO DE CAPITAL', 'PAGO INTERESES', 'COMISIONES BANCARIAS'
            ],
            'ACTIVO_FIJO': [
                'CAMION', 'CAMIONETA', 'EQUIPO DE TELEFONÍA', 'ERP', 'GRUA', 
                'MAQUINARIA', 'OFICINA', 'EQUIPO DE COMPUTO'
            ],
            'INGRESO': [
                'INGRESO', 'DEV PRESTAMO', 'VENTA DE SERVICIOS', 'VENTA DE MATERIAL', 
                'PRESTAMO', 'SPEI DEVUELTO', 'COMPRA DE DIVISAS'
            ],
            'BANCOS': [
                'COMISIONES BANCARIAS', 'COMPRA DE DIVISAS', 'FONDO DE INVERSION', 
                'TARJETA DE NEGOCIOS', 'SALDO INICIAL', 'TRASPASO ENTRE CUENTAS'
            ],
            'GASTOS_DE_OPERACION': [
                'ARTICULOS DE LIMPIEZA', 'CAJA CHICA', 'COMISION DE VENTA', 'COMPRA DE MATERIAL', 
                'DIESEL', 'FLETE', 'GASOLINA', 'MANTENIMIENTO', 'NOMINA', 'PENSION', 
                'PERMISOS AMBINTALES', 'RENTA', 'SEGURO', 'VIATICOS', 'CASETAS', 
                'PAGO TRANSPORTE', 'REFACCIONES', 'IMSS E INFONAVIT'
            ]
        }

        for cat_nombre, subcats in catalogo.items():
            cat_obj, _ = Categoria.objects.get_or_create(nombre=cat_nombre)
            for sub in subcats:
                SubCategoria.objects.get_or_create(categoria=cat_obj, nombre=sub)

        self.stdout.write(self.style.SUCCESS('¡Carga de catálogo completada con éxito!'))