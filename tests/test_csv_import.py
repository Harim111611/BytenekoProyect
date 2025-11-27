import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

import pandas as pd

# Probar cada archivo
archivos = [
    'encuesta_satisfaccion_clientes.csv',
    'encuesta_clima_laboral.csv',
    'encuesta_satisfaccion_universitaria.csv',
    'encuesta_hospital_servicios.csv',
    'encuesta_hotel_huespedes.csv'
]

for archivo in archivos:
    print(f"\n{'='*60}")
    print(f"Probando: {archivo}")
    print('='*60)
    
    try:
        # Intentar leer con diferentes codificaciones
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        df = None
        
        for encoding in encodings:
            try:
                df = pd.read_csv(archivo, encoding=encoding)
                print(f"✓ Leído con codificación: {encoding}")
                break
            except Exception as e:
                continue
        
        if df is None:
            print(f"✗ No se pudo leer el archivo")
            continue
        
        print(f"  Filas: {len(df)}")
        print(f"  Columnas: {len(df.columns)}")
        print(f"  Columnas: {list(df.columns)}")
        
        # Verificar si hay columnas problemáticas
        for col in df.columns:
            col_lower = col.lower()
            if 'fecha' in col_lower or 'date' in col_lower or 'periodo' in col_lower:
                print(f"  → Columna de fecha: {col}")
                print(f"    Valores muestra: {df[col].head(3).tolist()}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*60)
print("Prueba completada")
