# ternium/management/commands/import_remisiones.py
import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime

# Importa todos los modelos necesarios de tu aplicación
from ternium.models import (
    Remision, Empresa, LineaTransporte, Operador,
    Material, Unidad, Contenedor, Lugar, DetalleRemision
)

class Command(BaseCommand):
    help = 'Importa remisiones desde un archivo CSV.'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, help='Ruta al archivo CSV de remisiones')

    def handle(self, *args, **kwargs):
        file_path = kwargs['path']
        if not file_path:
            self.stdout.write(self.style.ERROR('Debes proporcionar la ruta al archivo CSV usando --path.'))
            return

        try:
            # Leer el archivo CSV
            self.stdout.write(f'Cargando datos desde: {file_path}...')
            df = pd.read_csv(
                file_path,
                dtype={'FOLIO FACTURA': str, 'COMENTARIO': str, 'PLACA CNT': str, 'CONT': str},
                parse_dates=['FECHA', 'INICIA LD', 'INICIA DLV']
            )

            # Renombrar columnas del CSV para que coincidan con los modelos
            df.rename(columns={
                'REMISION': 'remision', 'FECHA': 'fecha', 'ORIGEN ': 'origen',
                'DESTINO': 'destino', 'TRANS': 'linea_transporte_nombre',
                'OPERADOR': 'operador_nombre', 'ECO UNIDAD': 'unidad_nombre',
                'PLACAS': 'unidad_placas', 'CONT': 'contenedor_nombre',
                'PLACAS CNT': 'contenedor_placas', 'MATERIAL': 'material_nombre',
                'DESCRIPCION': 'descripcion', 'FOLIO LD': 'folio_ld',
                'PESO LD': 'peso_ld', 'INICIA LD': 'inicia_ld',
                'INICIA DLV': 'inicia_dlv', 'FOLIO DLV': 'folio_dlv',
                'PESO DLV': 'peso_dlv', 'COMENTARIO': 'comentario',
                'FOLIO FACTURA': 'folio_factura'
            }, inplace=True)
            df.dropna(subset=['remision'], inplace=True)

            remisiones_creadas = 0
            detalles_creados = 0

            with transaction.atomic():
                self.stdout.write(self.style.SUCCESS('Iniciando la importación de remisiones...'))

                for index, row in df.iterrows():
                    try:
                        # 1. Obtener o crear los objetos relacionados (ForeignKey)
                        # Asumimos que la empresa es la misma que la linea_transporte
                        empresa, _ = Empresa.objects.get_or_create(nombre=str(row['linea_transporte_nombre']).strip())
                        
                        linea_transporte, _ = LineaTransporte.objects.get_or_create(
                            nombre=str(row['linea_transporte_nombre']).strip(), empresa=empresa
                        )
                        operador, _ = Operador.objects.get_or_create(nombre=str(row['operador_nombre']).strip())
                        
                        unidad, _ = Unidad.objects.get_or_create(
                            nombre=str(row['unidad_nombre']).strip(),
                            placas=str(row['unidad_placas']).strip(),
                            empresa=empresa
                        )
                        
                        contenedor = None
                        if pd.notna(row['contenedor_nombre']) or pd.notna(row['contenedor_placas']):
                            contenedor, _ = Contenedor.objects.get_or_create(
                                nombre=str(row['contenedor_nombre']).strip(),
                                placas=str(row['contenedor_placas']).strip(),
                                empresa=empresa
                            )
                        
                        origen, _ = Lugar.objects.get_or_create(
                            nombre=str(row['origen']).strip(),
                            tipo='ORIGEN'
                            # Se asume que no todas las empresas tienen origen, o que se asocia después
                        )
                        destino, _ = Lugar.objects.get_or_create(
                            nombre=str(row['destino']).strip(),
                            tipo='DESTINO'
                        )
                        
                        material, _ = Material.objects.get_or_create(
                            nombre=str(row['material_nombre']).strip(),
                            empresa=empresa
                        )

                        # 2. Verificar si la remisión ya existe para evitar duplicados
                        remision_number = str(row['remision']).strip()
                        if Remision.objects.filter(remision=remision_number, empresa=empresa).exists():
                            self.stdout.write(self.style.WARNING(f'Saltando remisión duplicada: {remision_number}'))
                            continue

                        # 3. Crear el objeto Remision principal
                        remision_obj = Remision.objects.create(
                            remision=remision_number,
                            empresa=empresa,
                            fecha=row['fecha'].date(),
                            linea_transporte=linea_transporte,
                            operador=operador,
                            unidad=unidad,
                            contenedor=contenedor,
                            origen=origen,
                            destino=destino,
                            inicia_ld=row['inicia_ld'],
                            termina_ld=None,  # No existe en el CSV
                            folio_ld=str(row['folio_ld']),
                            descripcion=str(row['descripcion']),
                            inicia_dlv=row['inicia_dlv'],
                            termina_dlv=None, # No existe en el CSV
                            folio_dlv=str(row['folio_dlv']),
                            comentario=str(row['comentario']) if pd.notna(row['comentario']) else '',
                            folio_factura=str(row['folio_factura']) if pd.notna(row['folio_factura']) else '',
                        )
                        remisiones_creadas += 1

                        # 4. Crear el objeto DetalleRemision
                        DetalleRemision.objects.create(
                            remision=remision_obj,
                            material=material,
                            peso_ld=row['peso_ld'],
                            peso_dlv=row['peso_dlv'],
                            # No hay cliente en el CSV, se deja por defecto
                        )
                        detalles_creados += 1
                        
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'Error al procesar la fila {index + 2}: {e}'))
                        raise e

            self.stdout.write(self.style.SUCCESS(f'\nImportación finalizada con éxito.'))
            self.stdout.write(self.style.SUCCESS(f'Remisiones creadas: {remisiones_creadas}'))
            self.stdout.write(self.style.SUCCESS(f'Detalles de remisión creados: {detalles_creados}'))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Archivo no encontrado en la ruta: {file_path}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ocurrió un error inesperado durante la importación: {e}'))