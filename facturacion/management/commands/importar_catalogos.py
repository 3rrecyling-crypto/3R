import os
import pandas as pd
from django.core.management.base import BaseCommand
from django.conf import settings
from facturacion.models import Estado, Municipio, Colonia, CodigoPostalFiscal

class Command(BaseCommand):
    help = 'Importa catálogos del SAT ajustado a nombres con ..xlsx'

    def handle(self, *args, **options):
        base_dir = os.path.join(settings.BASE_DIR, 'archivos_sat')
        
        self.stdout.write("--- INICIANDO IMPORTACIÓN (CORREGIDO) ---")
        
        if not os.path.exists(base_dir):
            self.stdout.write(self.style.ERROR(f"¡La carpeta '{base_dir}' no existe!"))
            return

        # Función que intenta leer con 1 punto (.xlsx) o 2 puntos (..xlsx)
        def leer_excel_flexible(nombre_base):
            # Intentar nombre exacto (ej. Catálogo de estados.xlsx)
            ruta1 = os.path.join(base_dir, nombre_base)
            # Intentar con doble punto (ej. Catálogo de estados..xlsx)
            nombre_doble = nombre_base.replace('.xlsx', '..xlsx')
            ruta2 = os.path.join(base_dir, nombre_doble)

            if os.path.exists(ruta2):
                ruta_final = ruta2
                nombre_final = nombre_doble
            elif os.path.exists(ruta1):
                ruta_final = ruta1
                nombre_final = nombre_base
            else:
                self.stdout.write(self.style.WARNING(f"⚠️  No encontrado: {nombre_base} (ni {nombre_doble})"))
                return pd.DataFrame()
            
            try:
                self.stdout.write(f"📖 Leyendo {nombre_final}...")
                return pd.read_excel(ruta_final, dtype=str)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error leyendo {nombre_final}: {e}"))
                return pd.DataFrame()

        # ==========================================
        # 1. ESTADOS
        # ==========================================
        self.stdout.write("\n1. --- ESTADOS ---")
        df = leer_excel_flexible('Catálogo de estados.xlsx')
        if not df.empty:
            objs = []
            nuevos = 0
            for _, row in df.iterrows():
                # Ajusta nombres según tus columnas
                clave = row.get('c_Estado')
                nombre = row.get('Nombre del estado') or row.get('Descripción')
                pais = row.get('c_Pais', 'MEX')

                if clave and not Estado.objects.filter(clave=clave).exists():
                    objs.append(Estado(clave=clave, nombre=nombre, pais=pais))
                    nuevos += 1
            Estado.objects.bulk_create(objs)
            self.stdout.write(self.style.SUCCESS(f"   ✅ Estados nuevos: {nuevos}"))

        # ==========================================
        # 2. MUNICIPIOS
        # ==========================================
        self.stdout.write("\n2. --- MUNICIPIOS ---")
        df = leer_excel_flexible('Catálogo de municipios.xlsx')
        if not df.empty:
            objs = []
            nuevos = 0
            estados_map = {e.clave: e for e in Estado.objects.all()}
            
            for _, row in df.iterrows():
                c_edo = row.get('c_Estado')
                c_mun = row.get('c_Municipio')
                nombre = row.get('Descripción') or row.get('Nombre del municipio')

                edo_obj = estados_map.get(c_edo)
                if edo_obj and c_mun:
                    if not Municipio.objects.filter(clave=c_mun, estado=edo_obj).exists():
                        objs.append(Municipio(estado=edo_obj, clave=c_mun, nombre=nombre))
                        nuevos += 1
            Municipio.objects.bulk_create(objs)
            self.stdout.write(self.style.SUCCESS(f"   ✅ Municipios nuevos: {nuevos}"))

        # ==========================================
        # 3. COLONIAS
        # ==========================================
        self.stdout.write("\n3. --- COLONIAS ---")
        # Nombres base (el script probará con .xlsx y ..xlsx)
        archivos_cols = [
            'Catálogo de colonias.xlsx', 
            'Catálogo de colonias 2.xlsx', 
            'Catálogo de colonias 3.xlsx'
        ]
        
        total_cols = 0
        lote_objs = []
        
        for archivo in archivos_cols:
            df = leer_excel_flexible(archivo)
            if df.empty: continue
            
            for _, row in df.iterrows():
                c_col = row.get('c_Colonia')
                cp = row.get('c_CodigoPostal')
                nombre = row.get('Nombre del asentamiento')

                if pd.notna(cp) and pd.notna(nombre):
                    lote_objs.append(Colonia(clave=c_col, codigo_postal=cp, nombre=nombre))
                
                if len(lote_objs) >= 5000:
                    Colonia.objects.bulk_create(lote_objs)
                    total_cols += len(lote_objs)
                    lote_objs = []
                    print(f"      > Guardadas {total_cols} colonias...")

        if lote_objs:
            Colonia.objects.bulk_create(lote_objs)
            total_cols += len(lote_objs)
        
        self.stdout.write(self.style.SUCCESS(f"   ✅ Total Colonias: {total_cols}"))

        # ==========================================
        # 4. CÓDIGOS POSTALES
        # ==========================================
        self.stdout.write("\n4. --- VINCULACIÓN CP -> MUNICIPIO ---")
        # Estos parecen tener nombre normal, pero usaremos la flexible por si acaso
        archivos_cp = [
            'c_CodigoPostal_Parte_1.xlsx', 
            'c_CodigoPostal_Parte_2.xlsx'
        ]
        
        total_cps = 0
        lote_objs = []
        
        self.stdout.write("   Cargando mapa de municipios...")
        estados_map = {e.clave: e for e in Estado.objects.all()}
        municipios_map = {} 
        for m in Municipio.objects.all():
            key = f"{m.estado.clave}-{m.clave}"
            municipios_map[key] = m

        if not municipios_map:
            self.stdout.write(self.style.ERROR("   ⚠️ ¡ALERTA! No hay municipios en BD. Esta parte fallará."))
        
        for archivo in archivos_cp:
            df = leer_excel_flexible(archivo)
            if df.empty: continue
            
            for _, row in df.iterrows():
                cp = row.get('c_CodigoPostal')
                c_edo = row.get('c_Estado')
                c_mun = row.get('c_Municipio')

                edo_obj = estados_map.get(c_edo)
                mun_obj = municipios_map.get(f"{c_edo}-{c_mun}")

                if edo_obj and mun_obj and cp:
                    # Chequeo rápido para no duplicar (si la tabla está vacía, esto es rápido)
                    if not CodigoPostalFiscal.objects.filter(codigo=cp).exists():
                         lote_objs.append(CodigoPostalFiscal(codigo=cp, estado=edo_obj, municipio=mun_obj))
                
                if len(lote_objs) >= 5000:
                    CodigoPostalFiscal.objects.bulk_create(lote_objs)
                    total_cps += len(lote_objs)
                    lote_objs = []
                    print(f"      > Vinculados {total_cps} CPs...")

        if lote_objs:
            CodigoPostalFiscal.objects.bulk_create(lote_objs)
            total_cps += len(lote_objs)

        self.stdout.write(self.style.SUCCESS(f"   ✅ Total Relaciones CP importadas: {total_cps}"))
            
        self.stdout.write("\n--- LISTO ---")