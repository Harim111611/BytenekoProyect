from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction, connection
from django.core.cache import cache
from django.db.models import Count
from django.db.models import Prefetch
from surveys.models import Question, AnswerOption
from core.mixins import OwnerRequiredMixin, EncuestaQuerysetMixin
from surveys.models import Survey
from core.utils.logging_utils import StructuredLogger, log_user_action
import time

logger = StructuredLogger('surveys')


def _fast_delete_surveys(cursor, survey_ids):
    """
    Eliminación verdaderamente rápida usando Subqueries SQL puras.
    Evita traer IDs a la memoria de Python (Round-trips innecesarios).
    Todo el trabajo se hace en la base de datos.
    """
    survey_ids = list(survey_ids)
    if not survey_ids:
        return
    
    # Preparamos los placeholders para los IDs de las encuestas
    placeholders = ','.join(['%s'] * len(survey_ids))
    params = survey_ids
    
    start_time = time.time()
    logger.info(f"[DELETE] 🚀 INICIANDO eliminación optimizada SQL de {len(survey_ids)} encuesta(s): {survey_ids}")
    print(f"[DELETE] 🚀 INICIANDO eliminación optimizada SQL de {len(survey_ids)} encuesta(s): {survey_ids}")  # Backup para consola
    logger.info("[DELETE][TEST] Logger de surveys funcionando correctamente en archivo de log.")
    
    # Inicializar variables de tiempo para evitar errores si hay excepciones
    qr_time = sr_time = ao_time = q_time = s_time = 0.0
    qr_count = sr_count = ao_count = q_count = s_count = 0
    
    try:
        # PostgreSQL specific: Deshabilitar triggers/constraints temporalmente
        # Si esto falla por permisos, seguimos con el borrado estándar (respeta FKs pero más lento)
        try:
            cursor.execute("SET session_replication_role = 'replica'")
        except Exception:
            pass  # Ignorar si no tenemos permisos, la eliminación funcionará pero validará FKs
    
        # 1. Eliminar QuestionResponses (La tabla más grande) - Usar subconsulta directa
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_questionresponse
            WHERE survey_response_id IN (
                SELECT id FROM surveys_surveyresponse 
                WHERE survey_id IN ({placeholders})
            )
        """, params)
        qr_count = cursor.rowcount
        qr_time = time.time() - step_start
        logger.info(f"[DELETE] 📊 Step 1 - QuestionResponse: {qr_count} filas en {qr_time:.2f}s")
        print(f"[DELETE] 📊 Step 1 - QuestionResponse: {qr_count} filas en {qr_time:.2f}s")  # Backup para consola
    
        # 2. Eliminar SurveyResponses
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_surveyresponse
            WHERE survey_id IN ({placeholders})
        """, params)
        sr_count = cursor.rowcount
        sr_time = time.time() - step_start
        logger.info(f"[DELETE] Step 2 - SurveyResponse: {sr_count} filas en {sr_time:.2f}s")
    
        # 3. Eliminar AnswerOptions (Opciones de respuesta) - Subconsulta a través de Question
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_answeroption
            WHERE question_id IN (
                SELECT id FROM surveys_question 
                WHERE survey_id IN ({placeholders})
            )
        """, params)
        ao_count = cursor.rowcount
        ao_time = time.time() - step_start
        logger.info(f"[DELETE] Step 3 - AnswerOption: {ao_count} filas en {ao_time:.2f}s")
    
        # 4. Eliminar Preguntas
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_question
            WHERE survey_id IN ({placeholders})
        """, params)
        q_count = cursor.rowcount
        q_time = time.time() - step_start
        logger.info(f"[DELETE] Step 4 - Question: {q_count} filas en {q_time:.2f}s")
    
        # 5. Eliminar la Encuesta
        step_start = time.time()
        cursor.execute(f"""
            DELETE FROM surveys_survey
            WHERE id IN ({placeholders})
        """, params)
        s_count = cursor.rowcount
        s_time = time.time() - step_start
        logger.info(f"[DELETE] Step 5 - Survey: {s_count} filas en {s_time:.2f}s")
    
    except Exception as e:
        # Log del error y re-lanzar para que el código superior lo maneje
        logger.error(f"[DELETE] ERROR durante eliminación: {e}", exc_info=True)
        print(f"[DELETE] ERROR durante eliminación: {e}")
        import traceback
        traceback.print_exc()
        raise  # Re-lanzar la excepción
    
    finally:
        # Restaurar integridad referencial
        try:
            cursor.execute("SET session_replication_role = 'origin'")
        except Exception:
            pass
            
    total_duration = time.time() - start_time
    logger.info(f"[DELETE] ✅ Eliminación completa: {len(survey_ids)} encuesta(s) en {total_duration:.2f}s")
    logger.info(f"[DELETE] Desglose: QR={qr_time:.2f}s ({qr_count} filas), SR={sr_time:.2f}s ({sr_count} filas), AO={ao_time:.2f}s ({ao_count} filas), Q={q_time:.2f}s ({q_count} filas), S={s_time:.2f}s ({s_count} filas)")

# --- Bulk delete surveys ---
@login_required
@require_POST
def bulk_delete_surveys_view(request):
    """Eliminación bulk ultra-rápida usando SQL crudo con señales deshabilitadas."""
    from django.core.cache import cache
    from surveys.signals import DisableSignals
    logger.info('[BULK_DELETE] Request recibido')
    survey_ids = request.POST.getlist('survey_ids')
    logger.info(f'[BULK_DELETE] survey_ids recibidos: {survey_ids}')
    if not survey_ids:
        logger.info('[BULK_DELETE] No se seleccionaron encuestas para eliminar')
        messages.error(request, 'No se seleccionaron encuestas para eliminar.')
        return redirect('surveys:list')
    # Validar propiedad y sanitizar IDs
    try:
        clean_ids = [int(sid) for sid in survey_ids]
        logger.info(f'[BULK_DELETE] clean_ids: {clean_ids}')
    except ValueError:
        logger.info('[BULK_DELETE] IDs inválidos')
        messages.error(request, 'IDs inválidos.')
        return redirect('surveys:list')

    # Verificar que pertenecen al usuario (ANTES de lanzar la tarea)
    owned_ids = list(Survey.objects.filter(
        id__in=clean_ids,
        author=request.user
    ).values_list('id', flat=True))
    logger.info(f'[BULK_DELETE] owned_ids: {owned_ids}')
    if not owned_ids:
        logger.info('[BULK_DELETE] No tienes permisos para eliminar las encuestas seleccionadas')
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'No tienes permisos para eliminar las encuestas seleccionadas.'}, status=403)
        messages.error(request, 'No tienes permisos para eliminar las encuestas seleccionadas.')
        return redirect('surveys:list')

    count = len(owned_ids)
    user_id = request.user.id

    # Lanzar tarea Celery asíncrona (o background thread si Celery está en modo eager)
    try:
        from surveys.tasks import delete_surveys_task, perform_delete_surveys
        from django.conf import settings
        import time
        enqueue_start = time.time()
        if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
            # Celery está configurado para ejecutar tareas de forma síncrona (tests/dev).
            # Ejecutamos la eliminación en un hilo de fondo para no bloquear la petición HTTP.
            import threading
            def _bg():
                try:
                    perform_delete_surveys(owned_ids, user_id)
                except Exception:
                    logger.exception('[BULK_DELETE] Error en background thread durante eliminación')
            threading.Thread(target=_bg, daemon=True).start()
            result = None
            enqueue_ms = int((time.time() - enqueue_start) * 1000)
            logger.info(f'[BULK_DELETE] Background-thread launch time: {enqueue_ms}ms for user_id={user_id}, encuestas={owned_ids}')
        else:
            # Enviar la tarea al broker en un hilo separado para evitar bloquear
            import threading

            def _send_task():
                try:
                    res = delete_surveys_task.delay(owned_ids, user_id)
                    enqueue_ms_inner = int((time.time() - enqueue_start) * 1000)
                    logger.info(f'[BULK_DELETE][THREAD] Tarea Celery enviada: {getattr(res, "id", "-unknown-")} for user_id={user_id}, encuestas={owned_ids} (enqueue {enqueue_ms_inner}ms)')
                except Exception:
                    logger.exception('[BULK_DELETE][THREAD] Error enviando tarea Celery, cayendo a perform_delete_surveys')
                    try:
                        perform_delete_surveys(owned_ids, user_id)
                    except Exception:
                        logger.exception('[BULK_DELETE][THREAD] Error en perform_delete_surveys fallback')

            threading.Thread(target=_send_task, daemon=True).start()
            enqueue_ms = int((time.time() - enqueue_start) * 1000)
            logger.info(f'[BULK_DELETE] Tarea Celery encolada en hilo (no bloqueante) for user_id={user_id}, encuestas={owned_ids} (spawn {enqueue_ms}ms)')
        # Invalidate dashboard cache and adjust per-user survey count optimistically
        try:
            cache.delete(f"dashboard_data_user_{user_id}")
            # If there is a numeric cached count, decrement it optimistically so header counters don't jump
            count_key = f"survey_count_user_{user_id}"
            try:
                cur = cache.get(count_key)
                if isinstance(cur, int) and cur > 0:
                    cache.set(count_key, max(0, cur - count), timeout=300)
                else:
                    cache.delete(count_key)
            except Exception:
                # Fallback: remove the key so next render recalculates
                try:
                    cache.delete(count_key)
                except Exception:
                    pass
        except Exception:
            pass
    except Exception as e:
        logger.error(f"[BULK_DELETE] Error lanzando tarea Celery: {e}", exc_info=True)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': f'Error lanzando tarea de eliminación: {str(e)}'}, status=500)
        messages.error(request, f"Error lanzando tarea de eliminación: {str(e)}")
        return redirect('surveys:list')

    # Responder según tipo de petición
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': f'Se eliminarán {count} encuestas en segundo plano.'})
    if count == 1:
        messages.success(request, 'La encuesta se eliminará en segundo plano. Puedes continuar usando la plataforma.')
    else:
        messages.success(request, f'Se eliminarán {count} encuestas en segundo plano. Puedes continuar usando la plataforma.')
    return redirect('surveys:list')

    logger.info(f'[BULK_DELETE] Tarea programada para borrado de {count} encuestas (en background)')

class EncuestaListView(LoginRequiredMixin, EncuestaQuerysetMixin, ListView):
    """Vista lista de encuestas del usuario actual."""
    model = Survey
    template_name = 'surveys/list.html'
    context_object_name = 'surveys'

    def get_queryset(self):
        """Optimiza el queryset anotando conteos para evitar N+1 queries en templates.

        Añade `total_respuestas` y `total_preguntas` al queryset para usar
        directamente en la plantilla sin llamar a `related.count()` por cada
        elemento.
        """
        qs = super().get_queryset()
        return qs.annotate(
            total_respuestas=Count('responses', distinct=True),
            total_preguntas=Count('questions', distinct=True),
        )

class EncuestaDetailView(LoginRequiredMixin, OwnerRequiredMixin, DetailView):
    """Vista detalle de encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/detail.html'
    context_object_name = 'survey'

    def get_queryset(self):
        # 🚀 OPTIMIZACIÓN: Pre-carga preguntas y opciones para evitar N+1 en el template
        return super().get_queryset().prefetch_related(
            Prefetch(
                'questions',
                queryset=Question.objects.order_by('order').prefetch_related(
                    Prefetch('options', queryset=AnswerOption.objects.order_by('order'))
                )
            )
        )

class EncuestaCreateView(LoginRequiredMixin, CreateView):
    """Vista para crear nueva encuesta."""
    model = Survey
    template_name = 'surveys/survey_create.html'
    fields = ['title', 'description', 'status', 'category']
    success_url = reverse_lazy('surveys:list')

    def form_valid(self, form):
        form.instance.author = self.request.user
        log_user_action(
            'create_survey',
            success=True,
            user_id=self.request.user.id,
            survey_title=form.instance.title,
            category=form.instance.category
        )

        # Invalidate user dashboard cache so counters update immediately
        try:
            cache.delete(f"dashboard_data_user_{self.request.user.id}")
            cache.delete(f"survey_count_user_{self.request.user.id}")
        except Exception:
            pass
        return super().form_valid(form)

class EncuestaUpdateView(LoginRequiredMixin, OwnerRequiredMixin, UpdateView):
    """Vista para actualizar encuesta (solo creador)."""
    model = Survey
    fields = ['title', 'description', 'status']
    template_name = 'surveys/form.html'
    success_url = reverse_lazy('surveys:list')

class EncuestaDeleteView(LoginRequiredMixin, OwnerRequiredMixin, DeleteView):
    """Vista para eliminar encuesta (solo creador)."""
    model = Survey
    template_name = 'surveys/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')
    
    def delete(self, request, *args, **kwargs):
        from django.core.cache import cache
        from surveys.signals import DisableSignals
        
        # CRÍTICO: Deshabilitar señales ANTES de cualquier operación que pueda dispararlas
        # Incluso antes de get_object() para evitar cargar relaciones que disparen señales
        from surveys.signals import are_signals_enabled
        print(f"[DELETE] Señales habilitadas ANTES de DisableSignals: {are_signals_enabled()}")
        with DisableSignals():
            print(f"[DELETE] Señales habilitadas DENTRO de DisableSignals: {are_signals_enabled()}")
            # Obtener el objeto dentro del contexto de señales deshabilitadas
            survey = self.get_object()
            survey_id = survey.id
            author_id = survey.author.id if survey.author else None

            # Encolar siempre la eliminación en Celery para evitar bloqueos en el front
            try:
                from surveys.tasks import delete_surveys_task, perform_delete_surveys
                from django.conf import settings
                import time
                enqueue_start = time.time()
                if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
                    import threading
                    def _bg_single():
                        try:
                            perform_delete_surveys([survey_id], author_id)
                        except Exception:
                            logger.exception(f"[DELETE] Error en background thread borrando encuesta {survey_id}")
                    threading.Thread(target=_bg_single, daemon=True).start()
                    result = None
                    enqueue_ms = int((time.time() - enqueue_start) * 1000)
                    logger.info(f"[DELETE] Encuesta {survey_id} background-thread launch time: {enqueue_ms}ms (dev eager mode)")
                else:
                    import threading

                    def _send_single():
                        try:
                            res = delete_surveys_task.delay([survey_id], author_id)
                            enqueue_ms_inner = int((time.time() - enqueue_start) * 1000)
                            logger.info(f"[DELETE][THREAD] Encuesta {survey_id} tarea enviada: {getattr(res, 'id', '-')} (enqueue {enqueue_ms_inner}ms)")
                        except Exception:
                            logger.exception(f"[DELETE][THREAD] Error enviando tarea Celery para encuesta {survey_id}, cayendo a perform_delete_surveys")
                            try:
                                perform_delete_surveys([survey_id], author_id)
                            except Exception:
                                logger.exception(f"[DELETE][THREAD] Error en perform_delete_surveys fallback para encuesta {survey_id}")

                    threading.Thread(target=_send_single, daemon=True).start()
                    enqueue_ms = int((time.time() - enqueue_start) * 1000)
                    logger.info(f"[DELETE] Encuesta {survey_id} encolada en hilo (no bloqueante) (spawn {enqueue_ms}ms)")
                # Invalidate dashboard cache and adjust per-user survey count optimistically
                try:
                    cache.delete(f"dashboard_data_user_{author_id}")
                    count_key = f"survey_count_user_{author_id}"
                    try:
                        cur = cache.get(count_key)
                        if isinstance(cur, int) and cur > 0:
                            cache.set(count_key, max(0, cur - 1), timeout=300)
                        else:
                            cache.delete(count_key)
                    except Exception:
                        try:
                            cache.delete(count_key)
                        except Exception:
                            pass
                except Exception:
                    pass

                messages.success(request, 'La encuesta se eliminará en segundo plano. Puedes continuar usando la plataforma.')
                return redirect(self.success_url)
            except Exception as e:
                logger.error(f"[DELETE] Error lanzando tarea Celery para encuesta {survey_id}: {e}", exc_info=True)
                messages.error(request, f"Error lanzando tarea de eliminación: {str(e)}")
                return redirect(self.success_url)
        
        # Invalidar caché UNA SOLA VEZ después de la eliminación (no N veces)
        # CRÍTICO: delete_pattern es MUY lento con muchos keys, así que solo invalidamos claves específicas
        if author_id:
            cache.delete(f"dashboard_data_user_{author_id}")
            try:
                # Solo invalidar claves específicas conocidas (rápido)
                cache.delete(f"survey_stats_{survey_id}")
                # delete_pattern es MUY lento, así que lo omitimos
                # Las claves de análisis se invalidarán naturalmente al expirar o al regenerarse
                # cache.delete_pattern(f"survey_analysis_{survey_id}_*")  # MUY LENTO - omitido
                # cache.delete_pattern(f"survey_results_{survey_id}_*")  # MUY LENTO - omitido
                # cache.delete_pattern(f"pdf_report_{survey_id}_*")  # MUY LENTO - omitido
                # cache.delete_pattern(f"pptx_report_{survey_id}_*")  # MUY LENTO - omitido
            except Exception:
                pass
        
        messages.success(request, 'Encuesta eliminada correctamente.')
        return redirect(self.success_url)
