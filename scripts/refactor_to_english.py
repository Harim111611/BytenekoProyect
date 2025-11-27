"""
Script to refactor Spanish code to English throughout the codebase.
This will update all model references and field names in Python files.
"""
import os
import re
from pathlib import Path

# Model name mappings
MODEL_MAPPINGS = {
    'Encuesta': 'Survey',
    'Pregunta': 'Question',
    'OpcionRespuesta': 'AnswerOption',
    'RespuestaEncuesta': 'SurveyResponse',
    'RespuestaPregunta': 'QuestionResponse',
}

# Field name mappings for each model
FIELD_MAPPINGS = {
    # Survey fields
    'titulo': 'title',
    'descripcion': 'description',
    'categoria': 'category',
    'estado': 'status',
    'creador': 'author',
    'objetivo_muestra': 'sample_goal',
    'fecha_creacion': 'created_at',
    'fecha_modificacion': 'updated_at',
    
    # Question fields
    'encuesta': 'survey',
    'texto': 'text',
    'tipo': 'type',
    'es_obligatoria': 'is_required',
    'orden': 'order',
    
    # AnswerOption fields
    'pregunta': 'question',
    # 'texto': 'text',  # Already mapped above
    
    # SurveyResponse fields
    # 'encuesta': 'survey',  # Already mapped
    'usuario': 'user',
    'creado_en': 'created_at',  # Duplicate but ok
    'anonima': 'is_anonymous',
    
    # QuestionResponse fields
    'respuesta_encuesta': 'survey_response',
    # 'pregunta': 'question',  # Already mapped
    'opcion': 'selected_option',
    'valor_texto': 'text_value',
    'valor_numerico': 'numeric_value',
}

# Related name mappings
RELATED_NAME_MAPPINGS = {
    'preguntas': 'questions',
    'opciones': 'options',
    'respuestas': 'responses',
    'respuestas_pregunta': 'question_responses',
}

# Constant name mappings
CONSTANT_MAPPINGS = {
    'ESTADO_CHOICES': 'STATUS_CHOICES',
    'TIPO_CHOICES': 'TYPE_CHOICES',
}

def should_skip_file(filepath):
    """Check if file should be skipped"""
    skip_patterns = [
        'migrations/',
        '__pycache__/',
        '.pyc',
        'refactor_to_english.py',
        'venv/',
        'env/',
        '.venv/',  # Add .venv
        'site-packages/',  # Skip installed packages
        '.git/',
    ]
    filepath_str = str(filepath)
    return any(pattern in filepath_str for pattern in skip_patterns)

def refactor_file(filepath):
    """Refactor a single Python file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Replace model names in imports and class references
        for old_name, new_name in MODEL_MAPPINGS.items():
            # Replace in imports
            content = re.sub(rf'\bfrom\s+\.models\s+import\s+.*\b{old_name}\b', 
                           lambda m: m.group(0).replace(old_name, new_name), content)
            content = re.sub(rf'\bfrom\s+surveys\.models\s+import\s+.*\b{old_name}\b',
                           lambda m: m.group(0).replace(old_name, new_name), content)
            
            # Replace class references (but not in strings)
            content = re.sub(rf'\b{old_name}\.objects\b', f'{new_name}.objects', content)
            content = re.sub(rf'\bmodel\s*=\s*{old_name}\b', f'model = {new_name}', content)
        
        # Replace field names (more conservative - only in common patterns)
        for old_field, new_field in FIELD_MAPPINGS.items():
            # Replace in filter(), get(), create(), etc.
            content = re.sub(rf'(\w+)={old_field}\b', rf'\1={new_field}', content)
            content = re.sub(rf'\b{old_field}=', f'{new_field}=', content)
            
            # Replace in dot notation (obj.field)
            content = re.sub(rf'\.{old_field}(\s|\)|,|\.)', rf'.{new_field}\1', content)
        
        # Replace related_name
        for old_related, new_related in RELATED_NAME_MAPPINGS.items():
            content = re.sub(rf"related_name\s*=\s*['\"]{ old_related}['\"]", 
                           f"related_name='{new_related}'", content)
            # Also replace in access patterns like obj.preguntas.all()
            content = re.sub(rf'\.{old_related}\.', f'.{new_related}.', content)
        
        # Replace constants
        for old_const, new_const in CONSTANT_MAPPINGS.items():
            content = re.sub(rf'\b{old_const}\b', new_const, content)
        
        # Write back if changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Refactored: {filepath}")
            return True
        else:
            print(f"⏭️  No changes: {filepath}")
            return False
            
    except Exception as e:
        print(f"❌ Error in {filepath}: {e}")
        return False

def main():
    """Main refactoring process"""
    project_root = Path(__file__).parent
    python_files = list(project_root.rglob('*.py'))
    
    refactored_count = 0
    skipped_count = 0
    
    print(f"\n🔄 Starting refactoring process...")
    print(f"📁 Found {len(python_files)} Python files\n")
    
    for filepath in python_files:
        if should_skip_file(filepath):
            skipped_count += 1
            continue
        
        if refactor_file(filepath):
            refactored_count += 1
    
    print(f"\n✅ Refactoring complete!")
    print(f"📊 Files refactored: {refactored_count}")
    print(f"📊 Files skipped: {skipped_count}")
    print(f"📊 Files unchanged: {len(python_files) - refactored_count - skipped_count}")

if __name__ == '__main__':
    main()
