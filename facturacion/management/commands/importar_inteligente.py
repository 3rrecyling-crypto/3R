import os
import glob
import pandas as pd
import django

# --- CONFIGURACIÓN DJANGO ---
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'r3_recycling.settings')
django.setup()

from facturacion.models import CatalogoSAT

def run():
    print("🚀 INICIANDO IMPORTACIÓN DESDE EXCEL (.xlsx)...")
    print(f"📂 Carpeta: {os.getcwd()}")
    
    # 1. Buscar archivos Excel
    archivos = glob.glob("*.xlsx")
    
    if not archivos:
        print("❌ ERROR: No encontré archivos .xlsx en esta carpeta.")
        return

    print(f"🔎 Encontré {len(archivos)} archivos Excel. Procesando...")
    
    total_guardado = 0

    for archivo in archivos:
        try:
            print(f"\n📂 Leyendo: {archivo} ...")
            # Leemos el Excel. dtype=str asegura que '01' no se convierta en '1'
            df = pd.read_excel(archivo, dtype=str)
            
            # Normalizar encabezados (quitar espacios y BOM)
            df.columns = df.columns.str.strip()
            cols = df.columns.tolist()
            
            tipo_detectado = None
            col_clave = None
            col_desc = None

            # --- DETECCIÓN AUTOMÁTICA ---
            if 'c_ClaveProdServ' in cols:
                tipo_detectado = 'ClaveProdServ'
                col_clave = 'c_ClaveProdServ'
                col_desc = 'Descripción'
            elif 'c_ClaveUnidad' in cols:
                tipo_detectado = 'ClaveUnidad'
                col_clave = 'c_ClaveUnidad'
                # A veces se llama 'Nombre' o 'Descripción' en el Excel
                col_desc = 'Nombre' if 'Nombre' in cols else 'Descripción'
            
            if not tipo_detectado:
                print(f"   ⚠️ Saltando archivo: No detecté columnas clave (c_ClaveProdServ o c_ClaveUnidad).")
                continue

            print(f"   ✅ Detectado como: {tipo_detectado}")
            
            # Preparar objetos para guardar
            lote = []
            claves_vistas = set()
            
            # Recorrer filas
            for index, row in df.iterrows():
                raw_key = row[col_clave]
                
                # Validación básica
                if pd.isna(raw_key) or str(raw_key).lower() == 'nan':
                    continue
                
                clave = str(raw_key).strip()
                if clave.endswith('.0'): clave = clave[:-2] # Corregir "10101.0"
                
                if clave in claves_vistas: continue
                claves_vistas.add(clave)
                
                # Obtener descripción
                desc = "Sin descripción"
                if col_desc in row and not pd.isna(row[col_desc]):
                    desc = str(row[col_desc]).strip()

                lote.append(CatalogoSAT(
                    tipo=tipo_detectado,
                    clave=clave,
                    descripcion=desc[:255]
                ))
                
                # Guardar por lotes de 5000
                if len(lote) >= 5000:
                    CatalogoSAT.objects.bulk_create(lote, ignore_conflicts=True)
                    total_guardado += len(lote)
                    print(f"      -> {total_guardado} registros importados...")
                    lote = []

            # Guardar el resto
            if lote:
                CatalogoSAT.objects.bulk_create(lote, ignore_conflicts=True)
                total_guardado += len(lote)
            
            print(f"   🏁 Terminado {archivo}")

        except Exception as e:
            print(f"   ❌ Error leyendo {archivo}: {e}")

    print("\n===================================")
    print(f"🎉 TOTAL FINAL: {total_guardado} registros importados exitosamente.")

if __name__ == '__main__':
    run()