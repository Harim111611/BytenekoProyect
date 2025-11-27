import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings')
django.setup()

import pandas as pd
from django.db import transaction
from surveys.models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse
from django.contrib.auth.models import User
from core.validators import CSVImportValidator
from datetime import datetime

archivos = [
    'encuesta_clima_laboral.csv',
    'encuesta_satisfaccion_universitaria.csv',
    'encuesta_hospital_servicios.csv',
]

user = User.objects.first()

for csv_filename in archivos:
    print(f"\n{'='*80}")
    print(f"Procesando: {csv_filename}")
    print('='*80)
    
    try:
        # Leer archivo
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']
        df = None
        
        for encoding in encodings:
            try:
                df = pd.read_csv(csv_filename, encoding=encoding)
                print(f"✓ Leído con: {encoding}")
                break
            except:
                continue
        
        if df is None:
            print("✗ No se pudo leer")
            continue
        
        # Validar
        df = CSVImportValidator.validate_dataframe(df)
        print(f"✓ Validado: {len(df)} filas, {len(df.columns)} columnas")
        
        # Título
        base_name = csv_filename.rsplit('.', 1)[0]
        title = base_name.replace('_', ' ').replace('-', ' ').title()
        print(f"Título: {title}")
        
        # Detectar columnas
        date_col = None
        preguntas = []
        
        for col in df.columns:
            col_lower = col.lower()
            
            if not date_col and any(x in col_lower for x in ['fecha', 'date', 'periodo', 'visita', 'checkout']):
                date_col = col
                print(f"  Fecha: {col}")
                continue
            
            if col_lower == 'id':
                print(f"  Saltar ID exacto: {col}")
                continue
            
            sample = df[col].dropna()
            if len(sample) == 0:
                print(f"  Saltar vacía: {col}")
                continue
            
            unique_count = sample.nunique()
            if pd.api.types.is_numeric_dtype(sample):
                tipo = 'scale'
            elif unique_count <= 20:
                tipo = 'single'
            else:
                tipo = 'text'
            
            preguntas.append((col, tipo, unique_count))
            print(f"  Pregunta: {col} (type={tipo}, únicos={unique_count})")
        
        print(f"\n✓ Total preguntas a crear: {len(preguntas)}")
        
        # Simular creación (SIN guardar realmente)
        print(f"✓ Se crearían {len(df)} respuestas")
        print("✓ SIMULACIÓN EXITOSA")
        
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*80}")
print("Prueba completada")
