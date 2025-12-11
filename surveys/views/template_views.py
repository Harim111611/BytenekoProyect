from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.db import transaction
from surveys.models import SurveyTemplate
import json

@login_required
@require_http_methods(["POST"])
def create_template(request):
    """Crea una nueva plantilla de encuesta basada en un JSON."""
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        category = data.get('category', 'General')
        structure = data.get('structure', [])

        # Validaciones
        if not title:
            return JsonResponse({'success': False, 'error': 'El título es obligatorio'}, status=400)
        
        if not structure or not isinstance(structure, list):
            return JsonResponse({'success': False, 'error': 'La plantilla debe tener al menos una pregunta válida (structure).'}, status=400)

        with transaction.atomic():
            template = SurveyTemplate.objects.create(
                title=title,
                description=description,
                category=category,
                structure=structure
            )
            
        return JsonResponse({'success': True, 'id': template.id})
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
def list_templates(request):
    """Lista las plantillas disponibles (campos ligeros)."""
    try:
        # Optimizamos la query trayendo solo lo necesario
        templates = list(SurveyTemplate.objects.all().values(
            'id', 'title', 'description', 'category', 'structure', 'created_at'
        ).order_by('-created_at'))
        return JsonResponse(templates, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["PUT", "PATCH"])
def update_template(request, template_id):
    """Actualiza una plantilla existente."""
    template = get_object_or_404(SurveyTemplate, id=template_id)
    
    try:
        data = json.loads(request.body)
        
        with transaction.atomic():
            template.title = data.get('title', template.title)
            template.description = data.get('description', template.description)
            template.category = data.get('category', template.category)
            
            # Solo actualizamos la estructura si se envía y es válida
            new_structure = data.get('structure')
            if new_structure is not None:
                if isinstance(new_structure, list) and len(new_structure) > 0:
                    template.structure = new_structure
                else:
                    return JsonResponse({'success': False, 'error': 'La estructura no puede estar vacía'}, status=400)

            template.save()
            
        return JsonResponse({'success': True})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["DELETE", "POST"]) 
def delete_template(request, template_id):
    """
    Elimina una plantilla. 
    Se permite POST también para mayor compatibilidad si el frontend lo requiere,
    aunque el estándar es DELETE.
    """
    try:
        template = get_object_or_404(SurveyTemplate, id=template_id)
        template.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)