from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.db import transaction
from surveys.models import SurveyTemplate
import json
from asgiref.sync import sync_to_async

@login_required
@require_http_methods(["POST"])
async def create_template(request):
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

        @sync_to_async
        def create_template_obj():
            with transaction.atomic():
                return SurveyTemplate.objects.create(
                    title=title,
                    description=description,
                    category=category,
                    structure=structure
                )
        template = await create_template_obj()
        return JsonResponse({'success': True, 'id': template.id})
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["GET"])
async def list_templates(request):
    """Lista las plantillas disponibles (campos ligeros)."""
    try:
        # Optimizamos la query trayendo solo lo necesario
        @sync_to_async
        def get_templates():
            return list(SurveyTemplate.objects.all().values(
                'id', 'title', 'description', 'category', 'structure', 'created_at'
            ).order_by('-created_at'))
        templates = await get_templates()
        return JsonResponse(templates, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_http_methods(["PUT", "PATCH"])
async def update_template(request, template_id):
    """Actualiza una plantilla existente."""
    template = await sync_to_async(get_object_or_404, thread_sensitive=True)(SurveyTemplate, id=template_id)
    try:
        data = json.loads(request.body)
        @sync_to_async
        def update_template_obj():
            with transaction.atomic():
                template.title = data.get('title', template.title)
                template.description = data.get('description', template.description)
                template.category = data.get('category', template.category)
                new_structure = data.get('structure')
                if new_structure is not None:
                    if isinstance(new_structure, list) and len(new_structure) > 0:
                        template.structure = new_structure
                    else:
                        return False
                template.save()
                return True
        updated = await update_template_obj()
        if updated is False:
            return JsonResponse({'success': False, 'error': 'La estructura no puede estar vacía'}, status=400)
        return JsonResponse({'success': True})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON inválido'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["DELETE", "POST"])
async def delete_template(request, template_id):
    """
    Elimina una plantilla. 
    Se permite POST también para mayor compatibilidad si el frontend lo requiere,
    aunque el estándar es DELETE.
    """
    try:
        template = await sync_to_async(get_object_or_404, thread_sensitive=True)(SurveyTemplate, id=template_id)
        @sync_to_async
        def delete_obj():
            template.delete()
        await delete_obj()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)