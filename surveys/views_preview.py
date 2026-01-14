import os
import tempfile

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

# cpp_csv es obligatorio para importación/preview
from tools.cpp_csv import pybind_csv as cpp_csv

@login_required
def import_csv_preview_view(request):
    """Vista AJAX para generar preview del CSV antes de importar (usando cpp_csv)."""
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            csv_file = request.FILES['csv_file']
            
            # Guardar archivo temporalmente
            tmp_path = None
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp:
                csv_file.seek(0)
                for chunk in csv_file.chunks():
                    tmp.write(chunk)
                tmp.flush()
                tmp_path = tmp.name
            
            # Leer con cpp_csv (rápido y eficiente, con límite de muestra)
            sample_size = min(getattr(settings, "SURVEY_IMPORT_SAMPLE_SIZE", 1000), 1000)
            rows = cpp_csv.read_csv_dicts(tmp_path)[:sample_size]
            
            if not rows:
                return JsonResponse({
                    'success': True, 
                    'filename': csv_file.name, 
                    'total_rows': 0, 
                    'total_columns': 0, 
                    'columns': [], 
                    'sample_rows': []
                })
            
            # Analizar columnas
            columns_names = list(rows[0].keys())
            columns = []
            
            for col in columns_names:
                # Obtener valores únicos (muestra)
                values = [str(row.get(col, '')) for row in rows if row.get(col, '')]
                unique_values = list(set(values))[:3]
                
                columns.append({
                    'name': col,
                    'display_name': str(col).replace('_', ' ').title(),
                    'type': 'text',
                    'unique_values': len(set(values)),
                    'sample_values': unique_values,
                    'is_metadata': False
                })
            
            # Crear sample_rows (primeros 5 registros)
            sample_rows = []
            for row in rows[:5]:
                sample_rows.append([str(row.get(col, '')) for col in columns_names])
            
            return JsonResponse({
                'success': True,
                'filename': csv_file.name,
                'total_rows': len(rows),  # Nota: es el sample, no el total real
                'total_columns': len(columns_names),
                'columns': columns,
                'sample_rows': sample_rows
            })
        except Exception as e:
            # En producción conviene no filtrar detalles; mantenemos el mensaje por compat.
            return JsonResponse({'success': False, 'error': f'Error inesperado: {str(e)}'}, status=500)
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
    
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
