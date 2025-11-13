# surveys/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView
from django.views import View
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
import json
import csv
import io

# Importaciones para análisis de datos
from django.db.models import Count, Avg
from django.db.models.functions import TruncDate

# Importamos todos tus modelos
from .models import Encuesta, Pregunta, OpcionRespuesta, RespuestaEncuesta, RespuestaPregunta


# --- VISTA DE LISTA ---
class EncuestaListView(LoginRequiredMixin, ListView):
    model = Encuesta
    context_object_name = 'encuestas'
    template_name = 'surveys/list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Mostrar solo las encuestas del usuario logueado
        context['encuestas'] = Encuesta.objects.filter(creador=self.request.user)
        context['page_name'] = 'surveys'  # Para el sidebar
        return context


# --- VISTA DE CREACIÓN (ASISTENTE JS) ---
class EncuestaCreateView(LoginRequiredMixin, View):
    template_name = 'surveys/survey_create.html'

    def get(self, request, *args, **kwargs):
        """Maneja GET: Muestra la página del asistente."""
        context = {'page_name': 'surveys'}
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """Maneja POST: Recibe el JSON del JavaScript."""
        try:
            data = json.loads(request.body)
            info = data.get('surveyInfo')
            questions = data.get('questions')

            if not info or not questions or not info.get('titulo'):
                return JsonResponse({'error': 'Faltan datos de la encuesta o preguntas.'}, status=400)

            # 1. Crear la Encuesta
            encuesta = Encuesta.objects.create(
                creador=request.user,
                titulo=info.get('titulo'),
                descripcion=info.get('descripcion'),
                estado='draft',  # Todas las encuestas nuevas son Borrador
            )

            # 2. Crear las Preguntas y Opciones
            for i, q_data in enumerate(questions):
                tipo_valido = self.mapear_tipo_pregunta(q_data.get('tipo'))
                if tipo_valido not in dict(Pregunta.TIPO_CHOICES).keys():
                    raise Exception(f"Tipo de pregunta no válido: {tipo_valido}")

                pregunta = Pregunta.objects.create(
                    encuesta=encuesta,
                    texto=q_data.get('titulo'),
                    tipo=tipo_valido,
                    es_obligatoria=q_data.get('required', False),
                    orden=i
                )

                if q_data.get('opciones'):
                    for opt_texto in q_data.get('opciones'):
                        OpcionRespuesta.objects.create(pregunta=pregunta, texto=opt_texto)

            # 3. Devolver éxito y la URL para redirigir
            redirect_url = reverse_lazy('surveys:detail', kwargs={'pk': encuesta.pk})
            return JsonResponse({
                'success': True,
                'redirect_url': str(redirect_url)
            })

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Formato JSON inválido.'}, status=400)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def mapear_tipo_pregunta(self, tipo_js):
        # Mapea los tipos del JS ('text', 'scale') a los tipos del Modelo
        mapa = {
            'text': 'text',
            'number': 'number',
            'scale': 'scale',
            'single': 'single',
            'multi': 'multi',
        }
        return mapa.get(tipo_js, 'text')


# --- VISTA DE DETALLE (HUB) ---
class EncuestaDetailView(LoginRequiredMixin, DetailView):
    model = Encuesta
    context_object_name = 'encuesta'
    template_name = 'surveys/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_name'] = 'surveys'
        return context


# --- VISTA DE IMPORTACIÓN DE CSV ---
@login_required
def import_responses_view(request, pk):
    if request.method != 'POST':
        return redirect('surveys:detail', pk=pk)

    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)
    csv_file = request.FILES.get('csv_file')

    if not csv_file:
        messages.error(request, "No se seleccionó ningún archivo.")
        return redirect('surveys:detail', pk=pk)

    if not csv_file.name.endswith('.csv'):
        messages.error(request, "El archivo no es un CSV.")
        return redirect('surveys:detail', pk=pk)

    try:
        data = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(data))
        csv_headers = reader.fieldnames
        preguntas_map = {p.texto: p for p in encuesta.preguntas.all()}

        # Validar cabeceras
        for header in csv_headers:
            if header not in preguntas_map:
                messages.error(request,
                               f"La columna '{header}' del CSV no coincide con ninguna pregunta de la encuesta.")
                return redirect('surveys:detail', pk=pk)

        # Procesar filas
        respuestas_creadas = 0
        for row in reader:
            nueva_respuesta = RespuestaEncuesta.objects.create(
                encuesta=encuesta,
                anonima=True
            )
            for header, valor in row.items():
                if not valor:
                    continue
                pregunta_obj = preguntas_map[header]

                if pregunta_obj.tipo == 'text':
                    RespuestaPregunta.objects.create(
                        respuesta_encuesta=nueva_respuesta,
                        pregunta=pregunta_obj,
                        valor_texto=valor
                    )
                elif pregunta_obj.tipo == 'number' or pregunta_obj.tipo == 'scale':
                    RespuestaPregunta.objects.create(
                        respuesta_encuesta=nueva_respuesta,
                        pregunta=pregunta_obj,
                        valor_numerico=int(valor)
                    )
                elif pregunta_obj.tipo == 'single' or pregunta_obj.tipo == 'multi':
                    opcion_obj = OpcionRespuesta.objects.filter(pregunta=pregunta_obj, texto__iexact=valor).first()
                    if opcion_obj:
                        RespuestaPregunta.objects.create(
                            respuesta_encuesta=nueva_respuesta,
                            pregunta=pregunta_obj,
                            opcion=opcion_obj
                        )
            respuestas_creadas += 1

        messages.success(request, f"¡Éxito! Se importaron {respuestas_creadas} respuestas.")

    except Exception as e:
        messages.error(request, f"Ocurrió un error al procesar el archivo: {e}")

    return redirect('surveys:detail', pk=pk)


# --- VISTAS DE EDITAR Y BORRAR (SIMPLES) ---
class EncuestaUpdateView(LoginRequiredMixin, UpdateView):
    model = Encuesta
    fields = ['titulo', 'descripcion', 'estado', 'objetivo_muestra']
    template_name = 'surveys/form.html'
    success_url = reverse_lazy('surveys:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_name'] = 'surveys'
        return context


class EncuestaDeleteView(LoginRequiredMixin, DeleteView):
    model = Encuesta
    template_name = 'surveys/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_name'] = 'surveys'
        return context


# --- VISTA PÚBLICA PARA RESPONDER ---
def responder(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk)

    if encuesta.estado != 'active':
        return HttpResponse("Esta encuesta no está activa.", status=403)

    if request.method == 'POST':
        preguntas_obligatorias = encuesta.preguntas.filter(es_obligatoria=True)
        form_errors = []
        for pregunta in preguntas_obligatorias:
            post_key = f'pregunta_{pregunta.id}'
            if not request.POST.get(post_key) and not request.POST.getlist(post_key):
                form_errors.append(f"La pregunta '{pregunta.texto}' es obligatoria.")

        if form_errors:
            context = {'encuesta': encuesta, 'form_errors': form_errors}
            return render(request, 'surveys/fill.html', context)

        user = request.user if request.user.is_authenticated else None
        nueva_respuesta = RespuestaEncuesta.objects.create(
            encuesta=encuesta,
            usuario=user,
            anonima=not bool(user)
        )

        for pregunta in encuesta.preguntas.all():
            post_key = f'pregunta_{pregunta.id}'

            if pregunta.tipo == 'text':
                valor = request.POST.get(post_key)
                if valor:
                    RespuestaPregunta.objects.create(
                        respuesta_encuesta=nueva_respuesta,
                        pregunta=pregunta,
                        valor_texto=valor
                    )
            elif pregunta.tipo == 'number' or pregunta.tipo == 'scale':
                valor = request.POST.get(post_key)
                if valor:
                    RespuestaPregunta.objects.create(
                        respuesta_encuesta=nueva_respuesta,
                        pregunta=pregunta,
                        valor_numerico=int(valor)
                    )
            elif pregunta.tipo == 'single':
                opcion_id = request.POST.get(post_key)
                if opcion_id:
                    opcion = get_object_or_404(OpcionRespuesta, id=opcion_id)
                    RespuestaPregunta.objects.create(
                        respuesta_encuesta=nueva_respuesta,
                        pregunta=pregunta,
                        opcion=opcion
                    )
            elif pregunta.tipo == 'multi':
                opcion_ids = request.POST.getlist(post_key)
                for opcion_id in opcion_ids:
                    opcion = get_object_or_404(OpcionRespuesta, id=opcion_id)
                    RespuestaPregunta.objects.create(
                        respuesta_encuesta=nueva_respuesta,
                        pregunta=pregunta,
                        opcion=opcion
                    )

        return redirect('surveys:thanks')

    context = {'encuesta': encuesta}
    return render(request, 'surveys/fill.html', context)


# --- VISTA DE RESULTADOS (ANÁLISIS) ---
@login_required
def resultados(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)

    total_respuestas = RespuestaEncuesta.objects.filter(encuesta=encuesta).count()

    if total_respuestas == 0:
        context = {
            'encuesta': encuesta,
            'total_respuestas': 0,
            'page_name': 'surveys'
        }
        return render(request, 'surveys/results.html', context)

    # 1. KPI: Promedio de Satisfacción (preguntas tipo 'scale')
    avg_satisfaccion = RespuestaPregunta.objects.filter(
        pregunta__encuesta=encuesta,
        pregunta__tipo='scale'
    ).aggregate(promedio=Avg('valor_numerico'))
    kpi_prom_satisfaccion = avg_satisfaccion.get('promedio', 0) or 0

    # 2. Gráfico de Tendencia (Line)
    trend_query = RespuestaEncuesta.objects.filter(encuesta=encuesta) \
        .annotate(date=TruncDate('creado_en')) \
        .values('date') \
        .annotate(count=Count('id')) \
        .order_by('date')

    trend_data = {
        'labels': [item['date'].strftime('%Y-%m-%d') for item in trend_query],
        'data': [item['count'] for item in trend_query]
    }

    # 3. Gráfico de Ejemplo (Pie)
    pie_data = {'labels': [], 'data': [], 'question_title': 'N/A'}
    pie_question = encuesta.preguntas.filter(tipo='single').first()

    if pie_question:
        pie_query = RespuestaPregunta.objects.filter(pregunta=pie_question) \
            .values('opcion__texto') \
            .annotate(count=Count('id')) \
            .order_by('-count')

        pie_data = {
            'question_title': pie_question.texto,
            'labels': [item['opcion__texto'] for item in pie_query if item['opcion__texto']],
            'data': [item['count'] for item in pie_query if item['opcion__texto']]
        }

    # 4. Análisis por Pregunta (Bucle principal)
    analysis_data = []

    for pregunta in encuesta.preguntas.all().order_by('orden'):
        data_dict = {
            "pregunta_id": pregunta.id,
            "pregunta_texto": pregunta.texto,
            "pregunta_tipo": pregunta.get_tipo_display(),
            "tipo": pregunta.tipo,
            "respuestas": [],
            "chart_labels": [],
            "chart_data": [],
            "promedio": 0
        }

        if pregunta.tipo == 'text':
            respuestas_texto = RespuestaPregunta.objects.filter(pregunta=pregunta, valor_texto__isnull=False) \
                .values('valor_texto').exclude(valor_texto__exact='') \
                .order_by('-id')[:5]
            data_dict['respuestas'] = list(respuestas_texto)

        elif pregunta.tipo == 'number' or pregunta.tipo == 'scale':
            scale_query = RespuestaPregunta.objects.filter(pregunta=pregunta, valor_numerico__isnull=False) \
                .values('valor_numerico') \
                .annotate(count=Count('id')) \
                .order_by('valor_numerico')

            total_sum = sum(item['valor_numerico'] * item['count'] for item in scale_query)
            total_count = sum(item['count'] for item in scale_query)
            data_dict['promedio'] = (total_sum / total_count) if total_count > 0 else 0

            if pregunta.tipo == 'scale':
                rango = range(1, 11)
                counts_map = {item['valor_numerico']: item['count'] for item in scale_query}
                data_dict['chart_labels'] = [str(i) for i in rango]
                data_dict['chart_data'] = [counts_map.get(i, 0) for i in rango]
            else:
                data_dict['chart_labels'] = [item['valor_numerico'] for item in scale_query]
                data_dict['chart_data'] = [item['count'] for item in scale_query]

        elif pregunta.tipo == 'single' or pregunta.tipo == 'multi':
            opcion_query = RespuestaPregunta.objects.filter(pregunta=pregunta, opcion__isnull=False) \
                .values('opcion__texto') \
                .annotate(count=Count('id')) \
                .order_by('-count')

            data_dict['chart_labels'] = [item['opcion__texto'] for item in opcion_query]
            data_dict['chart_data'] = [item['count'] for item in opcion_query]

        analysis_data.append(data_dict)

    context = {
        'encuesta': encuesta,
        'total_respuestas': total_respuestas,
        'kpi_prom_satisfaccion': kpi_prom_satisfaccion,
        'trend_data': json.dumps(trend_data),
        'pie_data': json.dumps(pie_data),
        'analysis_data': analysis_data,
        'analysis_data_json': json.dumps(analysis_data),
        'page_name': 'surveys'
    }
    return render(request, 'surveys/results.html', context)


# --- VISTA DE EXPORTACIÓN A CSV ---
@login_required
def export_csv(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)

    response = HttpResponse(
        content_type='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename="encuesta_{encuesta.titulo.replace(" ", "_")}.csv"'},
    )

    writer = csv.writer(response)

    # Escribir cabeceras
    preguntas = list(encuesta.preguntas.all().order_by('orden'))
    headers = ['ID_Respuesta', 'Fecha'] + [p.texto for p in preguntas]
    writer.writerow(headers)

    respuestas_encuesta = encuesta.respuestas.all().prefetch_related(
        'respuestas_pregunta',
        'respuestas_pregunta__opcion'
    )

    for respuesta in respuestas_encuesta:
        row = [respuesta.id, respuesta.creado_en.strftime('%Y-%m-%d %H:%M:%S')]

        respuestas_map = {
            rp.pregunta_id: rp for rp in respuesta.respuestas_pregunta.all()
        }

        for p in preguntas:
            respuesta_pregunta = respuestas_map.get(p.id)

            if not respuesta_pregunta:
                row.append('')
            elif respuesta_pregunta.opcion:
                row.append(respuesta_pregunta.opcion.texto)
            elif respuesta_pregunta.valor_numerico is not None:
                row.append(respuesta_pregunta.valor_numerico)
            elif respuesta_pregunta.valor_texto:
                row.append(respuesta_pregunta.valor_texto)
            else:
                row.append('')

        writer.writerow(row)

    return response


# --- VISTA DE "GRACIAS" ---
def thanks_view(request):
    return render(request, 'surveys/thanks.html')