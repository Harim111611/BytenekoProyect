# surveys/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView, CreateView
from django.views import View
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder
from django.core.cache import cache
from django.utils import timezone
from django.db.models.functions import TruncDate
from django.db.models import Count, Avg, Min, Max
from django.db import transaction

import json
import csv
import io
import collections
import re
import base64
from datetime import datetime

# Ciencia de Datos
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

from .models import Encuesta, Pregunta, OpcionRespuesta, RespuestaEncuesta, RespuestaPregunta
from core.views import generate_vertical_bar_chart, generate_horizontal_bar_chart, generate_heatmap_chart


# ============================================================
# CLASES UTILITARIAS
# ============================================================
class Echo:
    def write(self, value): return value


# ============================================================
# 1. MOTOR DE ANÁLISIS (EL CEREBRO)
# ============================================================

def core_survey_analysis(encuesta, respuestas_qs, filters=None):
    total_respuestas = respuestas_qs.count()

    result = {
        "total_respuestas": total_respuestas,
        "nps_score": None, "nps_estado": "N/A",
        "analysis_data": [],
        "trend_data": {"labels": [], "data": []},
        "heatmap_image": None, "crosstab_html": None,
        "metrics": {"promedio_satisfaccion": 0, "ultima_respuesta": None}
    }

    if total_respuestas == 0:
        return result

    valores = RespuestaPregunta.objects.filter(respuesta_encuesta__in=respuestas_qs).values(
        'respuesta_encuesta__id',
        'respuesta_encuesta__creado_en',
        'pregunta__id',
        'pregunta__texto',
        'pregunta__tipo',
        'valor_texto', 'valor_numerico', 'opcion__texto'
    )

    df_raw = pd.DataFrame(list(valores))
    df = pd.DataFrame()

    if not df_raw.empty:
        df_raw['valor'] = df_raw['valor_numerico'].fillna(df_raw['opcion__texto']).fillna(df_raw['valor_texto'])

        df = df_raw.pivot_table(
            index='respuesta_encuesta__id',
            columns='pregunta__texto',
            values='valor',
            aggfunc='first'
        )
        fechas = df_raw.groupby('respuesta_encuesta__id')['respuesta_encuesta__creado_en'].first()
        df['Fecha'] = fechas

        if filters:
            for col, val in filters.items():
                if col in df.columns and val:
                    try:
                        df = df[df[col].astype(str).str.lower().str.contains(str(val).lower(), na=False)]
                    except Exception:
                        pass

            result['total_respuestas'] = len(df)
            if df.empty: return result

    # --- ANÁLISIS GLOBAL ---
    if 'Fecha' in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df['Fecha']):
            df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')

        trend = df.groupby(df['Fecha'].dt.date).size()
        result['trend_data'] = {
            'labels': [d.strftime('%d %b') for d in trend.index],
            'data': trend.values.tolist()
        }
        result['metrics']['ultima_respuesta'] = df['Fecha'].max()

    pregunta_nps = encuesta.preguntas.filter(tipo='scale').first()
    if pregunta_nps and pregunta_nps.texto in df.columns:
        s_nps = pd.to_numeric(df[pregunta_nps.texto], errors='coerce').dropna()
        if not s_nps.empty:
            prom = (s_nps >= 9).sum()
            det = (s_nps <= 6).sum()
            score = round(((prom - det) / len(s_nps)) * 100, 1)
            result['nps_score'] = score
            if score >= 50:
                result['nps_estado'] = "Excelente"
            elif score > 0:
                result['nps_estado'] = "Bueno"
            elif score > -30:
                result['nps_estado'] = "Mejorable"
            else:
                result['nps_estado'] = "Crítico"

    scale_questions = encuesta.preguntas.filter(tipo='scale').values_list('texto', flat=True)
    valid_cols = [c for c in scale_questions if c in df.columns]
    if valid_cols:
        df_scales = df[valid_cols].apply(pd.to_numeric, errors='coerce')
        all_values = df_scales.values.flatten()
        valid_values = all_values[~np.isnan(all_values)]
        if valid_values.size > 0:
            result['metrics']['promedio_satisfaccion'] = round(valid_values.mean(), 1)

    if len(valid_cols) >= 2:
        result['heatmap_image'] = generate_heatmap_chart(df[valid_cols].apply(pd.to_numeric, errors='coerce'))

    for pregunta in encuesta.preguntas.all().order_by('orden'):
        col_name = pregunta.texto
        item = {
            "id": pregunta.id, "orden": pregunta.orden, "texto": pregunta.texto,
            "tipo": pregunta.tipo, "pregunta_tipo": pregunta.get_tipo_display(),
            "stats": {}, "chart_labels": [], "chart_data": [], "respuestas": [], "insight": "",
            "chart_image": None, "total_respuestas": 0
        }

        if col_name not in df.columns:
            result['analysis_data'].append(item)
            continue

        series = df[col_name].dropna()
        if series.empty:
            result['analysis_data'].append(item)
            continue

        item['total_respuestas'] = len(series)

        if pregunta.tipo == 'text':
            textos = series.astype(str).tolist()
            words, bigrams = analizar_texto_avanzado(textos)
            item["stats"]["top_words"] = words
            item["respuestas"] = [{"valor_texto": t} for t in textos[:50]]
            main = bigrams[0][0] if bigrams else (words[0][0] if words else "Variado")
            item["insight"] = f"Tema principal: <strong>'{main}'</strong>"

        elif pregunta.tipo in ['number', 'scale']:
            s_num = pd.to_numeric(series, errors='coerce').dropna()
            if not s_num.empty:
                desc = s_num.describe()
                item["stats"] = {
                    "promedio": desc['mean'], "minimo": desc['min'], "maximo": desc['max'],
                    "mediana": s_num.median(), "std": s_num.std()
                }

                if pregunta.tipo == 'scale':
                    avg = desc['mean']
                    real_max = s_num.max()
                    scale_cap = 5 if real_max <= 5 else 10
                    normalized_score = (avg / scale_cap) * 10
                    sent = "sobresaliente" if normalized_score >= 8.5 else (
                        "positivo" if normalized_score >= 7 else ("regular" if normalized_score >= 5 else "crítico"))
                    item["insight"] = f"Rendimiento <strong>{sent}</strong> ({avg:.1f}/{scale_cap})."
                    if pregunta == pregunta_nps: item['stats']['nps'] = result['nps_score']
                else:
                    item["insight"] = f"Promedio: <strong>{desc['mean']:.1f}</strong>."

                counts = s_num.value_counts().sort_index()
                if pregunta.tipo == 'scale':
                    limit_max = 5 if s_num.max() <= 5 else 10
                    counts = counts.reindex(range(0 if s_num.min() == 0 else 1, limit_max + 1), fill_value=0)
                item["chart_labels"] = [str(i) for i in counts.index]
                item["chart_data"] = counts.values.tolist()
                item['chart_image'] = generate_vertical_bar_chart(item["chart_labels"], item["chart_data"],
                                                                  "Distribución")

        elif pregunta.tipo in ['single', 'multi']:
            if pregunta.tipo == 'multi':
                all_opts = []
                for v in series: all_opts.extend([x.strip() for x in str(v).split(',')])
                counts = pd.Series(all_opts).value_counts()
            else:
                counts = series.value_counts()

            if not counts.empty:
                ganador = counts.index[0]
                total = counts.sum() if pregunta.tipo == 'multi' else len(series)
                porc = (counts.iloc[0] / total) * 100
                item["insight"] = f"La mayoría (<strong>{porc:.0f}%</strong>) prefiere <strong>{ganador}</strong>."
                item["chart_labels"] = counts.index.tolist()
                item["chart_data"] = counts.values.tolist()
                item['chart_image'] = generate_horizontal_bar_chart(item["chart_labels"], item["chart_data"],
                                                                    "Distribución")

        result['analysis_data'].append(item)
    return result


def analizar_texto_avanzado(textos_list):
    if not textos_list: return [], []
    text_full = " ".join(textos_list).lower()
    clean = re.sub(r'[^\w\s]', '', text_full)
    words = clean.split()
    stops = {'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'se', 'del', 'las', 'un', 'por', 'con', 'no', 'una', 'su',
             'para', 'es', 'al', 'lo', 'como', 'mas', 'pero', 'sus', 'le', 'ya', 'o', 'muy', 'sin', 'sobre', 'me', 'mi',
             'bueno', 'buena', 'malo', 'mala', 'yo', 'tu'}
    filtered = [w for w in words if w not in stops and len(w) > 2]
    bigrams = [f"{filtered[i]} {filtered[i + 1]}" for i in range(len(filtered) - 1)]
    return collections.Counter(filtered).most_common(5), collections.Counter(bigrams).most_common(3)


# ============================================================
# 2. VISTAS CRUD
# ============================================================
class EncuestaListView(LoginRequiredMixin, ListView):
    model = Encuesta
    template_name = 'surveys/list.html'
    context_object_name = 'encuestas'

    def get_queryset(self): return Encuesta.objects.filter(creador=self.request.user).order_by('-fecha_creacion')


class EncuestaCreateView(LoginRequiredMixin, CreateView):
    model = Encuesta
    template_name = 'surveys/survey_create.html'
    # Agregamos 'categoria' a los fields permitidos
    fields = ['titulo', 'descripcion', 'estado', 'categoria']
    success_url = reverse_lazy('surveys:list')

    def post(self, request, *args, **kwargs):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            try:
                data = json.loads(request.body)

                # Aquí guardamos la categoría que viene del JS (sea del select o del input 'otro')
                encuesta = Encuesta.objects.create(
                    creador=request.user,
                    titulo=data['surveyInfo']['titulo'],
                    descripcion=data['surveyInfo']['descripcion'],
                    categoria=data['surveyInfo'].get('categoria', 'General'), # Captura
                    estado='draft'
                )

                # ... (resto de creación de preguntas igual) ...

                for i, q in enumerate(data['questions']):
                    tipo = {'text': 'text', 'number': 'number', 'scale': 'scale', 'single': 'single', 'multi': 'multi'}.get(q['tipo'], 'text')
                    p = Pregunta.objects.create(encuesta=encuesta, texto=q['titulo'], tipo=tipo, orden=i, es_obligatoria=q.get('required', False))
                    if q.get('opciones'):
                        for opt in q['opciones']: OpcionRespuesta.objects.create(pregunta=p, texto=opt)

                return JsonResponse({'success': True, 'redirect_url': str(reverse_lazy('surveys:detail', kwargs={'pk': encuesta.pk}))})
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.creador = self.request.user
        return super().form_valid(form)

class EncuestaDetailView(LoginRequiredMixin, DetailView):
    model = Encuesta
    template_name = 'surveys/detail.html'
    context_object_name = 'encuesta'


class EncuestaUpdateView(LoginRequiredMixin, UpdateView):
    model = Encuesta
    fields = ['titulo', 'descripcion', 'estado']
    template_name = 'surveys/form.html'
    success_url = reverse_lazy('surveys:list')


class EncuestaDeleteView(LoginRequiredMixin, DeleteView):
    model = Encuesta
    template_name = 'surveys/confirm_delete.html'
    success_url = reverse_lazy('surveys:list')


# ============================================================
# 3. IMPORTACIÓN (CORREGIDO: FECHAS ROBUSTAS)
# ============================================================

@login_required
def import_new_survey_view(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            messages.error(request, f"Error al leer el CSV: {e}")
            return redirect('surveys:list')

        title = request.POST.get('survey_title') or f"Importada {csv_file.name}"
        try:
            with transaction.atomic():
                encuesta = Encuesta.objects.create(creador=request.user, titulo=title,
                                                   descripcion=f"Importada {datetime.now().strftime('%Y-%m-%d')}",
                                                   estado='active', objetivo_muestra=len(df))
                col_map = {}
                date_col_name = None

                # 1. Detectar columnas
                for i, col in enumerate(df.columns):
                    if not date_col_name and any(
                            x in col.lower() for x in ['fecha', 'date', 'timestamp', 'time', 'creado']):
                        date_col_name = col
                        col_map[col] = 'TIMESTAMP'
                        continue

                    sample = df[col].dropna()
                    dtype = 'text'
                    if pd.api.types.is_numeric_dtype(sample):
                        dtype = 'scale' if sample.min() >= 0 and sample.max() <= 10 else 'number'
                    elif not sample.empty:
                        if sample.astype(str).str.contains(',').any():
                            dtype = 'multi'
                        elif sample.nunique() < 15:
                            dtype = 'single'
                    pregunta = Pregunta.objects.create(encuesta=encuesta, texto=col.replace('_', ' ').title(),
                                                       tipo=dtype, orden=i)
                    col_map[col] = pregunta
                    if dtype in ['single', 'multi']:
                        unique_ops = set()
                        for val in sample:
                            if dtype == 'single':
                                unique_ops.add(val)
                            else:
                                unique_ops.update([x.strip() for x in str(val).split(',')])
                        for op in unique_ops: OpcionRespuesta.objects.get_or_create(pregunta=pregunta,
                                                                                    texto=str(op)[:255])

                # 2. Cargar datos (Row by Row para asegurar fechas)
                respuestas_encuesta_list = []

                for _, row in df.iterrows():
                    created_at = timezone.now()  # Default

                    # FIX: Parseo de fecha explicito y robusto
                    if date_col_name:
                        val_date = row[date_col_name]
                        if pd.notnull(val_date):
                            try:
                                # Intentar convertir string a datetime
                                dt = pd.to_datetime(val_date)
                                if not pd.isna(dt):
                                    py_dt = dt.to_pydatetime()
                                    if timezone.is_naive(py_dt):
                                        created_at = timezone.make_aware(py_dt)
                                    else:
                                        created_at = py_dt
                            except Exception:
                                pass  # Si falla, usa now()

                    r = RespuestaEncuesta(encuesta=encuesta, anonima=True)
                    r.creado_en = created_at  # Asignar la fecha histórica
                    respuestas_encuesta_list.append(r)

                objs_creados = RespuestaEncuesta.objects.bulk_create(respuestas_encuesta_list)

                rp_list = []
                for i, (index, row) in enumerate(df.iterrows()):
                    resp_obj = objs_creados[i]
                    for col, preg in col_map.items():
                        if preg == 'TIMESTAMP': continue
                        val = row[col]
                        if pd.isna(val) or val == '': continue
                        rp = RespuestaPregunta(respuesta_encuesta=resp_obj, pregunta=preg)
                        if preg.tipo in ['number', 'scale']:
                            try:
                                rp.valor_numerico = int(val)
                            except:
                                pass
                        elif preg.tipo == 'single':
                            op = OpcionRespuesta.objects.filter(pregunta=preg, texto=str(val)).first()
                            if op: rp.opcion = op
                        else:
                            rp.valor_texto = str(val)
                        rp_list.append(rp)

                RespuestaPregunta.objects.bulk_create(rp_list, batch_size=2000)
            messages.success(request, f"Importación exitosa: {len(df)} registros.")
        except Exception as e:
            messages.error(request, f"Error: {e}")
    return redirect('surveys:list')


@login_required
def export_csv(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)

    def rows_generator():
        pseudo_buffer = Echo()
        writer = csv.writer(pseudo_buffer)
        yield u'\ufeff'
        preguntas = list(encuesta.preguntas.all().order_by('orden'))
        yield writer.writerow(['ID', 'Fecha', 'Usuario'] + [p.texto for p in preguntas])

        respuestas_qs = RespuestaEncuesta.objects.filter(encuesta=encuesta).select_related('usuario').prefetch_related(
            'respuestas_pregunta__pregunta', 'respuestas_pregunta__opcion').iterator(chunk_size=1000)
        for resp in respuestas_qs:
            row = [resp.id, resp.creado_en.strftime('%Y-%m-%d %H:%M'),
                   resp.usuario.username if resp.usuario else 'Anónimo']
            rmap = {}
            for r in resp.respuestas_pregunta.all():
                val = r.valor_texto or r.valor_numerico or (r.opcion.texto if r.opcion else '')
                rmap[r.pregunta_id] = str(val)
            for p in preguntas: row.append(rmap.get(p.id, ''))
            yield writer.writerow(row)

    filename = f"resultados_{encuesta.id}.csv"
    response = StreamingHttpResponse(rows_generator(), content_type="text/csv; charset=utf-8")
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def import_responses_view(request, pk): return redirect('surveys:detail', pk=pk)


def responder(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk)
    if request.method == 'POST':
        with transaction.atomic():
            usuario = request.user if request.user.is_authenticated else None
            respuesta = RespuestaEncuesta.objects.create(encuesta=encuesta, usuario=usuario, anonima=(usuario is None))
            for p in encuesta.preguntas.all():
                field = f'pregunta_{p.id}'
                if p.tipo == 'multi':
                    opts = request.POST.getlist(field)
                    txts = [OpcionRespuesta.objects.get(id=o).texto for o in opts if
                            OpcionRespuesta.objects.filter(id=o).exists()]
                    if txts: RespuestaPregunta.objects.create(respuesta_encuesta=respuesta, pregunta=p,
                                                              valor_texto=",".join(txts))
                else:
                    val = request.POST.get(field)
                    if val:
                        if p.tipo in ['number', 'scale']:
                            RespuestaPregunta.objects.create(respuesta_encuesta=respuesta, pregunta=p,
                                                             valor_numerico=val)
                        elif p.tipo == 'single':
                            op = OpcionRespuesta.objects.filter(id=val).first()
                            if op: RespuestaPregunta.objects.create(respuesta_encuesta=respuesta, pregunta=p, opcion=op)
                        else:
                            RespuestaPregunta.objects.create(respuesta_encuesta=respuesta, pregunta=p, valor_texto=val)
        return redirect('surveys:thanks')
    return render(request, 'surveys/fill.html', {'encuesta': encuesta})


def thanks_view(request): return render(request, 'surveys/thanks.html')


@login_required
def resultados(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)
    respuestas_qs = RespuestaEncuesta.objects.filter(encuesta=encuesta)

    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    if start_date:
        try:
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            respuestas_qs = respuestas_qs.filter(creado_en__date__gte=s_date)
        except ValueError:
            pass

    if end_date:
        try:
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            respuestas_qs = respuestas_qs.filter(creado_en__date__lte=e_date)
        except ValueError:
            pass

    segment_col = request.GET.get('segment_col')
    segment_val = request.GET.get('segment_val')
    filters = {}
    if segment_col and segment_val:
        filters[segment_col] = segment_val

    # Cache de resultados analíticos por encuesta, usuario y filtros aplicados
    cache_sig = json.dumps({
        'start': start_date,
        'end': end_date,
        'segment_col': segment_col,
        'segment_val': segment_val,
    }, sort_keys=True)
    cache_key = f"survey_results:{request.user.id}:{encuesta.id}:{cache_sig}"

    data = cache.get(cache_key)
    if data is None:
        data = core_survey_analysis(encuesta, respuestas_qs, filters=filters)
        cache.set(cache_key, data, 300)

    analysis_json = json.dumps(data['analysis_data'], cls=DjangoJSONEncoder)

    context = {
        'encuesta': encuesta, 'total_respuestas': data['total_respuestas'], 'metrics': data['metrics'],
        'nps_score': data['nps_score'], 'nps_estado': data['nps_estado'], 'trend_data': json.dumps(data['trend_data']),
        'analysis_data': data['analysis_data'], 'analysis_data_json': analysis_json,
        'heatmap_image': data['heatmap_image'], 'crosstab_html': data['crosstab_html'],
        'top_insights': data['analysis_data'][:3], 'page_name': 'surveys',
        'filter_start': start_date, 'filter_end': end_date, 'filter_col': segment_col, 'filter_val': segment_val,
        'preguntas_filtro': encuesta.preguntas.filter(tipo__in=['single', 'multi'])
    }
    return render(request, 'surveys/results.html', context)
