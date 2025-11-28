import pandas as pd
import re

df = pd.read_csv("data/samples/encuesta_hotel_huespedes.csv", encoding="utf-8-sig")
print("\n=== ANÁLISIS DETALLADO: encuesta_hotel_huespedes.csv ===")
print(f"Total columnas: {len(df.columns)}\n")

identity_patterns = [
    "nombre_completo", "full_name", "apellido", "apellidos",
    "^nombre$", "^name$", "nombre_", "name_",
    "email", "correo", "telefono", "phone",
    "dni", "cedula", "identificacion", "documento",
    "_id$", "reserva_id", "empleado_id", "paciente_id", "cliente_id",
    "nacionalidad", "genero", "sexo", "gender",
    "tipo_habitacion", "tipo_servicio", "tipo_",
    "^area$", "^departamento$", "^carrera$", "^semestre$", "^servicio$"
]

preguntas = 0
saltadas = 0

for col in df.columns:
    col_lower = col.lower()
    skip = False
    match_pattern = ""
    
    # Fecha
    if any(x in col_lower for x in ["fecha", "date", "checkout", "check_out"]):
        print(f"📅 {col:<30} -> FECHA (saltada)")
        saltadas += 1
        continue
    
    # ID
    if col_lower == "id" or "_id" in col_lower:
        print(f"🔑 {col:<30} -> ID (saltada)")
        saltadas += 1
        continue
    
    # Contexto
    for pattern in identity_patterns:
        if "^" in pattern or "$" in pattern:
            if re.search(pattern, col_lower):
                skip = True
                match_pattern = pattern
                break
        elif pattern in col_lower:
            skip = True
            match_pattern = pattern
            break
    
    if skip:
        print(f"👤 {col:<30} -> CONTEXTO (saltada) - patrón: {match_pattern}")
        saltadas += 1
    else:
        unique = df[col].nunique()
        tipo = "SCALE" if pd.api.types.is_numeric_dtype(df[col]) else ("SINGLE" if unique <= 20 else "TEXT")
        print(f"✅ {col:<30} -> PREGUNTA ({tipo}, {unique} vals)")
        preguntas += 1

print(f"\n📊 TOTAL: {preguntas} preguntas, {saltadas} saltadas")
