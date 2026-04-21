import os
import pandas as pd
from django.core.management.base import BaseCommand
from django.conf import settings
from facturacion.models import (
    SatRegimenFiscal, SatUsoCFDI, SatTipoComprobante, 
    SatObjetoImpuesto, SatImpuesto
)

class Command(BaseCommand):
    help = 'Carga inteligente de catálogos del SAT (Excel o CSV)'

    def handle(self, *args, **kwargs):
        base_dir = os.path.join(settings.BASE_DIR, 'sat_data')
        
        self.stdout.write(f"📂 Buscando archivos en: {base_dir}")

        if not os.path.exists(base_dir):
            self.stdout.write(self.style.ERROR(f"❌ La carpeta no existe: {base_dir}"))
            return

        all_files = os.listdir(base_dir)
        self.stdout.write(f"📄 Archivos en carpeta: {len(all_files)}")

        config = [
            {
                # CAMBIO AQUÍ: Usamos 'gimen' para que coincida con "Régimen" o "Regimen"
                'keywords': ['gimen'], 
                'model': SatRegimenFiscal, 
                'col_clave': 'c_RegimenFiscal', 
                'col_desc': 'Descripción'
            },
            {
                'keywords': ['uso'], 
                'model': SatUsoCFDI, 
                'col_clave': 'c_UsoCFDI', 
                'col_desc': 'Descripción'
            },
            {
                'keywords': ['tipo', 'comprobante'], 
                'model': SatTipoComprobante, 
                'col_clave': 'c_TipoDeComprobante', 
                'col_desc': 'Descripción'
            },
            {
                'keywords': ['objeto', 'impuesto'], 
                'model': SatObjetoImpuesto, 
                'col_clave': 'c_ObjetoImp', 
                'col_desc': 'Descripción'
            },
            {
                'keywords': ['impuestos'],
                'exclude': ['objeto'],
                'model': SatImpuesto, 
                'col_clave': 'c_Impuesto', 
                'col_desc': 'Descripción'
            },
        ]

        for conf in config:
            found_file = None
            for f in all_files:
                f_lower = f.lower()
                # Verifica si todas las keywords están en el nombre
                if all(k in f_lower for k in conf['keywords']):
                    # Verifica exclusiones
                    if 'exclude' in conf and any(e in f_lower for e in conf['exclude']):
                        continue
                    found_file = f
                    break
            
            if not found_file:
                # Mensaje de advertencia si no lo encuentra
                self.stdout.write(self.style.WARNING(f"⚠️  No encontré archivo para: {conf['model']._meta.verbose_name} (Buscaba: {conf['keywords']})"))
                continue

            file_path = os.path.join(base_dir, found_file)
            self.stdout.write(f"⚡ Procesando: {found_file}...")

            try:
                if found_file.endswith('.csv'):
                    df = pd.read_csv(file_path)
                else:
                    df = pd.read_excel(file_path)

                # Limpieza de columnas
                df.columns = df.columns.str.strip()
                
                model = conf['model']
                count = 0
                
                for index, row in df.iterrows():
                    # Obtener valores con seguridad
                    try:
                        clave = str(row[conf['col_clave']]).strip()
                        desc = str(row[conf['col_desc']]).strip()
                        
                        if clave and desc and clave.lower() != 'nan':
                            model.objects.update_or_create(
                                clave=clave,
                                defaults={'descripcion': desc}
                            )
                            count += 1
                    except KeyError as e:
                        # Si falla por nombre de columna, avisa pero sigue
                        self.stdout.write(self.style.ERROR(f"   Error de columna en fila {index}: {e}"))
                        break
                
                self.stdout.write(self.style.SUCCESS(f"✅ {count} guardados en {model.__name__}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error grave en {found_file}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS("\n🎉 --- PROCESO COMPLETADO ---"))