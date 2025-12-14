from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError

@csrf_exempt
@login_required
def import_csv_preview_view(request):
    """Vista AJAX para generar preview del CSV antes de importar."""
    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            csv_file = request.FILES['csv_file']
            # Leer DataFrame con detección automática de codificación
            encodings = [
                'utf-8-sig', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252', 'windows-1252'
            ]
            df = None
            for encoding in encodings:
                try:
                    csv_file.seek(0)
                    df = pd.read_csv(csv_file, encoding=encoding)
                    break
                except Exception:
                    continue
            if df is None:
                return JsonResponse({'success': False, 'error': 'No se pudo leer el archivo. Verifica el formato CSV.'}, status=400)
            # Validar DataFrame
            if df.empty or len(df.columns) == 0:
                return JsonResponse({'success': True, 'filename': csv_file.name, 'total_rows': 0, 'total_columns': 0, 'columns': [], 'sample_rows': []})
            # Analizar columnas
            columns = []
            for idx, col in enumerate(df.columns):
                sample = df[col].dropna().unique()[:3]
                columns.append({
                    'name': col,
                    'display_name': str(col).replace('_', ' ').title(),
                    'type': 'text',
                    'unique_values': int(df[col].nunique()),
                    'sample_values': [str(v) for v in sample],
                    'is_metadata': False
                })
            sample_rows = df.head(5).values.tolist()
            sample_rows = [[str(val) if not pd.isna(val) else '' for val in row] for row in sample_rows]
            return JsonResponse({
                'success': True,
                'filename': csv_file.name,
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'columns': columns,
                'sample_rows': sample_rows
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error inesperado: {str(e)}'}, status=500)
    return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
