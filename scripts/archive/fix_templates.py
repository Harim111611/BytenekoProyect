#!/usr/bin/env python
"""
Script para actualizar referencias en español a inglés en templates Django.
"""
import re
from pathlib import Path

# Mapeo de reemplazos
REPLACEMENTS = {
    # Variables de contexto
    r'\bencuestas\b': 'surveys',
    r'\bencuesta\.': 'survey.',
    r'\bencuesta\b': 'survey',
    r'\bpregunta\.': 'question.',
    r'\bpregunta\b': 'question',
    r'\bpreguntas\b': 'questions',
    r'\bopcion\.': 'option.',
    r'\bopcion\b': 'option',
    r'\bopciones\b': 'options',
    
    # Campos de modelo
    r'\.titulo\b': '.title',
    r'\.texto\b': '.text',
    r'\.estado\b': '.status',
    r'\.tipo\b': '.type',
    r'\.orden\b': '.order',
    r'\.es_obligatoria\b': '.is_required',
    r'\.valor_texto\b': '.text_value',
    r'\.valor_numerico\b': '.numeric_value',
}

def fix_template(file_path):
    """Aplica reemplazos a un archivo de template."""
    content = file_path.read_text(encoding='utf-8')
    original_content = content
    
    for pattern, replacement in REPLACEMENTS.items():
        content = re.sub(pattern, replacement, content)
    
    if content != original_content:
        file_path.write_text(content, encoding='utf-8')
        print(f"✓ Actualizado: {file_path.relative_to(Path.cwd())}")
        return True
    return False

def main():
    """Procesa todos los templates."""
    base_dir = Path(__file__).parent.parent
    templates_dir = base_dir / 'templates'
    
    count = 0
    for template_path in templates_dir.rglob('*.html'):
        if fix_template(template_path):
            count += 1
    
    print(f"\n{count} archivos actualizados")

if __name__ == '__main__':
    main()
