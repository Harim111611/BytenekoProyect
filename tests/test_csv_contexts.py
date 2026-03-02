"""
Script para verificar que la lógica de detección de contextos funciona
correctamente con todos los archivos CSV de ejemplo.
"""
import os
from pathlib import Path
import pandas as pd

def analyze_csv_structure(csv_path):
    """Analiza la estructura de un CSV y simula la lógica de detección de contextos."""
    print(f"\n{'='*80}")
    print(f"📄 Analizando: {os.path.basename(csv_path)}")
    print(f"{'='*80}")
    
    # Intentar leer con múltiples codificaciones
    encodings = [
        'utf-8-sig', 'utf-8', 'utf-16', 'utf-16-le', 'utf-16-be',
        'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252', 'mac_roman'
    ]
    
    df = None
    encoding_used = None
    
    for encoding in encodings:
        try:
            df = pd.read_csv(csv_path, encoding=encoding)
            encoding_used = encoding
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            print(f"❌ Error con codificación {encoding}")
            continue
    
    if df is None:
        print("❌ No se pudo leer el archivo con ninguna codificación")
        return None
    
    print(f"✅ Archivo leído correctamente con codificación: {encoding_used}")
    print(f"📊 Dimensiones: {len(df)} filas x {len(df.columns)} columnas")
    
    # Analizar cada columna
    print(f"\n{'Columna':<40} {'Tipo Detectado':<15} {'Valores Únicos':<15} {'Acción'}")
    print("-" * 90)
    
    date_col_name = None
    preguntas_creadas = 0
    columnas_saltadas = 0
    metadata_cols = []
    pregunta_cols = []
    
    for col in df.columns:
        col_lower = col.lower()
        
        # Patrones para saltar columnas de metadata
        skip_patterns = [
            'response_id', 'respuesta_id', 'id_respuesta',
            'timestamp', 'creado', 'created_at', 'updated_at'
        ]
        
        # Patrones para identificadores y nombres personales (solo datos contextuales puros)
        # IMPORTANTE: Esto solo debe saltar columnas que son IDENTIDAD, no evaluaciones
        identity_patterns = [
            # Nombres y apellidos (con variaciones)
            'nombre_completo', 'full_name', 'apellido', 'apellidos',
            '^nombre$', '^name$', 'nombre_', 'name_',  # nombre + sufijo
            # Contacto
            'email', 'correo', 'telefono', 'phone', 
            # Identificaciones
            'dni', 'cedula', 'identificacion', 'documento',
            '_id$', 'reserva_id', 'empleado_id', 'paciente_id', 'cliente_id',
            # Demográficos
            'nacionalidad', 'genero', 'sexo', 'gender', '^edad$',
            # Tipos y clasificaciones contextuales
            'tipo_habitacion', 'tipo_servicio', 'tipo_',
            '^area$', '^departamento$',
            '^carrera$', '^semestre$', '^servicio$'  # Solo exactos
        ]
        
        sample = df[col].dropna()
        unique_count = sample.nunique() if len(sample) > 0 else 0
        
        # Detectar columna de fecha/timestamp
        if not date_col_name and any(x in col_lower for x in ['fecha', 'date', 'timestamp', 'time', 'creado', 'periodo', 'checkout', 'check_out', 'visita', 'compra']):
            date_col_name = col
            tipo = '📅 TIMESTAMP'
            accion = '⏭️  SALTADA (fecha)'
            columnas_saltadas += 1
            metadata_cols.append((col, 'timestamp'))
        
        # Saltar IDs exactos o de respuesta
        elif col_lower == 'id' or any(pattern in col_lower for pattern in skip_patterns):
            tipo = '🔑 ID/METADATA'
            accion = '⏭️  SALTADA (ID)'
            columnas_saltadas += 1
            metadata_cols.append((col, 'id'))
        
        # Saltar columnas de identificación personal (usar regex para patrones exactos)
        else:
            import re
            skip_column = False
            for pattern in identity_patterns:
                # Si el patrón tiene ^ o $, usar regex exacto
                if '^' in pattern or '$' in pattern:
                    if re.search(pattern, col_lower):
                        skip_column = True
                        break
                # Si no, buscar substring simple
                elif pattern in col_lower:
                    skip_column = True
                    break
            
            if skip_column:
                tipo = '👤 CONTEXTO'
                accion = '⏭️  SALTADA (contexto)'
                columnas_saltadas += 1
                metadata_cols.append((col, 'context'))
        
        # Columna vacía
            elif len(sample) == 0:
                tipo = '⚠️  VACÍA'
                accion = '⏭️  SALTADA (vacía)'
                columnas_saltadas += 1
                metadata_cols.append((col, 'empty'))
        
        # Detectar tipo de pregunta
            else:
                if pd.api.types.is_numeric_dtype(sample):
                    if sample.min() >= 0 and sample.max() <= 10:
                        tipo = '📊 SCALE (0-10)'
                    else:
                        tipo = '🔢 NUMBER'
                elif unique_count <= 20:
                    tipo = f'📋 SINGLE ({unique_count})'
                else:
                    tipo = '📝 TEXT'
            
                accion = '✅ PREGUNTA'
                preguntas_creadas += 1
                pregunta_cols.append((col, tipo, unique_count))
        
        # Mostrar valores de muestra para las primeras columnas
        sample_vals = ""
        if len(sample) > 0 and unique_count <= 5:
            sample_vals = f" | Ej: {', '.join(str(v)[:20] for v in sample.unique()[:3])}"
        
        print(f"{col[:38]:<40} {tipo:<15} {unique_count:<15} {accion}{sample_vals}")
    
    # Resumen
    print(f"\n{'='*90}")
    print(f"📈 RESUMEN:")
    print(f"   • Total columnas: {len(df.columns)}")
    print(f"   • ✅ Preguntas creadas: {preguntas_creadas}")
    print(f"   • ⏭️  Columnas saltadas: {columnas_saltadas}")
    print(f"   • 📅 Columna de fecha: {date_col_name if date_col_name else 'No detectada'}")
    print(f"   • 📊 Total respuestas a importar: {len(df)}")
    
    # Detalle de columnas saltadas
    if metadata_cols:
        print(f"\n📋 Columnas saltadas por categoría:")
        context_cols = [c for c, t in metadata_cols if t == 'context']
        id_cols = [c for c, t in metadata_cols if t == 'id']
        timestamp_cols = [c for c, t in metadata_cols if t == 'timestamp']
        
        if context_cols:
            print(f"   • 👤 Contexto: {', '.join(context_cols)}")
        if id_cols:
            print(f"   • 🔑 IDs: {', '.join(id_cols)}")
        if timestamp_cols:
            print(f"   • 📅 Timestamp: {', '.join(timestamp_cols)}")
    
    # Detalle de preguntas
    if pregunta_cols:
        print(f"\n❓ Preguntas que se crearán:")
        for col, tipo, unique in pregunta_cols:
            print(f"   • {col} ({tipo})")
    
    return {
        'filename': os.path.basename(csv_path),
        'total_columns': len(df.columns),
        'preguntas': preguntas_creadas,
        'saltadas': columnas_saltadas,
        'respuestas': len(df),
        'encoding': encoding_used
    }


def main():
    """Analiza todos los archivos CSV de ejemplo."""
    base_dir = Path(__file__).parent
    
    csv_files = [
        'encuesta_clima_laboral.csv',
        'encuesta_hotel_huespedes.csv',
        'encuesta_hospital_servicios.csv',
        'encuesta_satisfaccion_clientes.csv',
        'encuesta_satisfaccion_universitaria.csv',
        'test_import.csv',
        'gran_dataset_10k.csv'
    ]
    
    print("🔍 ANÁLISIS DE DETECCIÓN DE CONTEXTOS EN CSV")
    print("=" * 90)
    print("Este script verifica que la lógica de importación identifique correctamente:")
    print("  ✓ Columnas de contexto (nombres, IDs, emails, etc.)")
    print("  ✓ Columnas de fecha/timestamp")
    print("  ✓ Preguntas de escala (numéricas 0-10)")
    print("  ✓ Preguntas de selección única (≤20 valores únicos)")
    print("  ✓ Preguntas de texto abierto")
    
    results = []
    for csv_file in csv_files:
        csv_path = base_dir / csv_file
        if csv_path.exists():
            result = analyze_csv_structure(csv_path)
            if result:
                results.append(result)
        else:
            print(f"\n⚠️  Archivo no encontrado: {csv_file}")
    
    # Resumen final
    print(f"\n\n{'='*90}")
    print("📊 RESUMEN GENERAL DE TODOS LOS ARCHIVOS")
    print(f"{'='*90}")
    print(f"{'Archivo':<45} {'Cols':<8} {'Preg.':<8} {'Salt.':<8} {'Resp.':<10} {'Encoding'}")
    print("-" * 90)
    
    for r in results:
        print(f"{r['filename']:<45} {r['total_columns']:<8} {r['preguntas']:<8} {r['saltadas']:<8} {r['respuestas']:<10} {r['encoding']}")
    
    print(f"\n✅ Análisis completado. Total de archivos procesados: {len(results)}")
    
    # Verificar casos problemáticos
    print(f"\n🔍 VERIFICACIÓN DE CASOS ESPECIALES:")
    for r in results:
        issues = []
        if r['saltadas'] == 0:
            issues.append("⚠️  No se saltó ninguna columna (posible problema)")
        if r['preguntas'] == 0:
            issues.append("❌ No se detectaron preguntas")
        if r['preguntas'] == r['total_columns']:
            issues.append("⚠️  Se crearon preguntas para todas las columnas (posible problema)")
        
        if issues:
            print(f"\n   {r['filename']}:")
            for issue in issues:
                print(f"      {issue}")
    
    if not any(r['saltadas'] == 0 or r['preguntas'] == 0 for r in results):
        print(f"\n   ✅ Todos los archivos procesados correctamente")


if __name__ == '__main__':
    main()
