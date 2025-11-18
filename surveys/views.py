# surveys/views.py
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, DeleteView
from django.views import View
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.core.serializers.json import DjangoJSONEncoder  # <-- IMPORTANTE
import json
import csv
import io
import collections
import re
import base64
from datetime import datetime

# --- IMPORTS DE CIENCIA DE DATOS ---
import pandas as pd
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

# Importaciones de Django
from django.db.models import Count, Avg, Min, Max, StdDev
from django.db.models.functions import TruncDate
from .models import Encuesta, Pregunta, OpcionRespuesta, RespuestaEncuesta, RespuestaPregunta


# ============================================================
# FUNCIONES AUXILIARES (Sin cambios)
# ============================================================
def generar_heatmap_correlacion(df):
    df_numeric = df.select_dtypes(include=['float64', 'int64'])
    if df_numeric.shape[1] < 2 or df_numeric.shape[0] < 2: return None
    plt.figure(figsize=(8, 6))
    sns.heatmap(df_numeric.corr(), annot=True, cmap='coolwarm', fmt=".2f", linewidths=.5, vmin=-1, vmax=1)
    plt.title('Relación entre variables', fontsize=10)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def calcular_nps(respuestas_qs):
    total = respuestas_qs.count()
    if total == 0: return None, "Sin datos"
    prom = respuestas_qs.filter(valor_numerico__gte=9).count()
    det = respuestas_qs.filter(valor_numerico__lte=6).count()
    score = round(((prom / total) * 100) - ((det / total) * 100), 1)
    if score >= 50:
        estado = "Excelente"
    elif score > 0:
        estado = "Bueno"
    elif score > -30:
        estado = "Mejorable"
    else:
        estado = "Crítico"
    return score, estado


def analizar_texto_avanzado(respuestas_qs):
    if isinstance(respuestas_qs, list):
        textos = [str(r['valor_texto']) for r in respuestas_qs if r.get('valor_texto')]
    else:
        textos = [r['valor_texto'] for r in respuestas_qs if r['valor_texto']]
    if not textos: return [], []
    texto_completo = " ".join(textos).lower()
    texto_limpio = re.sub(r'[^\w\s]', '', texto_completo)
    palabras = texto_limpio.split()
    ignorar = {'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'se', 'del', 'las', 'un', 'por', 'con', 'no', 'una',
               'su', 'para', 'es', 'al', 'lo', 'como', 'mas', 'pero', 'sus', 'le', 'ya', 'o', 'muy', 'sin', 'sobre',
               'me', 'mi', 'bueno', 'buena', 'malo', 'mala', 'yo', 'tu', 'nos', 'ha', 'si', 'porque', 'este', 'esta',
               'ese', 'esa'}
    palabras_filtradas = [p for p in palabras if p not in ignorar and len(p) > 2]
    top_palabras = collections.Counter(palabras_filtradas).most_common(5)
    bigramas = []
    for i in range(len(palabras) - 1):
        w1, w2 = palabras[i], palabras[i + 1]
        if w1 not in ignorar and w2 not in ignorar and len(w1) > 2 and len(w2) > 2: bigramas.append(f"{w1} {w2}")
    top_bigramas = collections.Counter(bigramas).most_common(3)
    return top_palabras, top_bigramas


def build_responses_df(encuesta, respuestas_orm):
    rows = []
    preguntas_cols = {p.id: p.texto for p in encuesta.preguntas.all()}
    for resp in respuestas_orm:
        row = {"Fecha": resp.creado_en.date()}
        for rp in resp.respuestas_pregunta.all():
            val = None
            if rp.pregunta.tipo in ["number", "scale"]:
                val = rp.valor_numerico
            elif rp.pregunta.tipo in ["single", "multi"] and rp.opcion:
                val = rp.opcion.texto
            elif rp.pregunta.tipo == "text":
                val = rp.valor_texto
            col_name = preguntas_cols.get(rp.pregunta.id)
            if col_name:
                if col_name in row and val is not None:
                    row[col_name] = f"{row[col_name]}, {val}"
                elif val is not None:
                    row[col_name] = val
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def compute_trend_data(respuestas_orm):
    trend_qs = respuestas_orm.annotate(date=TruncDate("creado_en")).values("date").annotate(count=Count("id")).order_by(
        "date")
    return {"labels": [r["date"].strftime("%d %b") for r in trend_qs], "data": [r["count"] for r in trend_qs]}


# ============================================================
# VISTAS CRUD Y OPERATIVAS (Sin cambios mayores)
# ============================================================
class EncuestaListView(LoginRequiredMixin, ListView):
    model = Encuesta
    context_object_name = 'encuestas'
    template_name = 'surveys/list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['encuestas'] = Encuesta.objects.filter(creador=self.request.user)
        context['page_name'] = 'surveys'
        return context


class EncuestaCreateView(LoginRequiredMixin, View):
    template_name = 'surveys/survey_create.html'

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, {'page_name': 'surveys'})

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            info = data.get('surveyInfo')
            questions = data.get('questions')
            if not info or not questions or not info.get('titulo'): return JsonResponse({'error': 'Faltan datos.'},
                                                                                        status=400)
            encuesta = Encuesta.objects.create(creador=request.user, titulo=info.get('titulo'),
                                               descripcion=info.get('descripcion'), estado='draft')
            for i, q_data in enumerate(questions):
                tipo_valido = self.mapear_tipo_pregunta(q_data.get('tipo'))
                pregunta = Pregunta.objects.create(encuesta=encuesta, texto=q_data.get('titulo'), tipo=tipo_valido,
                                                   es_obligatoria=q_data.get('required', False), orden=i)
                if q_data.get('opciones'):
                    for opt in q_data.get('opciones'): OpcionRespuesta.objects.create(pregunta=pregunta, texto=opt)
            return JsonResponse(
                {'success': True, 'redirect_url': str(reverse_lazy('surveys:detail', kwargs={'pk': encuesta.pk}))})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    def mapear_tipo_pregunta(self, tipo_js):
        return {'text': 'text', 'number': 'number', 'scale': 'scale', 'single': 'single', 'multi': 'multi'}.get(tipo_js,
                                                                                                                'text')


class EncuestaDetailView(LoginRequiredMixin, DetailView):
    model = Encuesta
    context_object_name = 'encuesta'
    template_name = 'surveys/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_name'] = 'surveys'
        return context


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


@login_required
def import_responses_view(request, pk):
    if request.method != 'POST': return redirect('surveys:detail', pk=pk)
    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)
    csv_file = request.FILES.get('csv_file')
    if not csv_file: return redirect('surveys:detail', pk=pk)
    try:
        data = csv_file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(data))
        pmap = {p.texto: p for p in encuesta.preguntas.all()}
        count = 0
        for row in reader:
            res = RespuestaEncuesta.objects.create(encuesta=encuesta, anonima=True)
            # Fecha histórica
            fecha_str = row.get('Fecha') or row.get('fecha')
            if fecha_str:
                try:
                    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                        try:
                            dt = datetime.strptime(fecha_str, fmt)
                            if timezone.is_naive(dt): dt = timezone.make_aware(dt)
                            res.creado_en = dt
                            res.save()
                            break
                        except:
                            continue
                except:
                    pass

            for h, v in row.items():
                if h.lower() in ['fecha', 'date', 'id'] or not v or h not in pmap: continue
                p = pmap[h]
                if p.tipo == 'text':
                    RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p, valor_texto=v)
                elif p.tipo in ['number', 'scale']:
                    try:
                        RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p,
                                                         valor_numerico=int(float(v)))
                    except:
                        pass
                elif p.tipo in ['single', 'multi']:
                    op = OpcionRespuesta.objects.filter(pregunta=p, texto__iexact=v).first()
                    if op: RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p, opcion=op)
            count += 1
        messages.success(request, f"Importadas {count} respuestas.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect('surveys:detail', pk=pk)


@login_required
def import_new_survey_view(request):
    if request.method != 'POST': return redirect('surveys:list')
    csv_file = request.FILES.get('csv_file')
    title = request.POST.get('survey_title')
    if not csv_file: return redirect('surveys:list')
    try:
        data = csv_file.read().decode('utf-8-sig')
        reader = csv.reader(io.StringIO(data))
        headers = next(reader)
        rows = list(reader)
        encuesta = Encuesta.objects.create(creador=request.user, titulo=title or csv_file.name.replace('.csv', ''),
                                           estado='active')
        preguntas = []
        fecha_idx = -1
        col_idxs = []
        for i, h in enumerate(headers):
            if h.lower() in ['fecha', 'date']:
                fecha_idx = i
                continue
            col_idxs.append(i)
            col_vals = [r[i] for r in rows if i < len(r) and r[i].strip()]
            tipo = 'text'
            if col_vals:
                try:
                    nums = [float(v) for v in col_vals]
                    if all(0 <= n <= 10 for n in nums):
                        tipo = 'scale'
                    else:
                        tipo = 'number'
                except:
                    pass
            preguntas.append(Pregunta.objects.create(encuesta=encuesta, texto=h, tipo=tipo, orden=len(preguntas)))

        count = 0
        for row in rows:
            res = RespuestaEncuesta.objects.create(encuesta=encuesta, anonima=True)
            if fecha_idx != -1 and fecha_idx < len(row):
                try:
                    dt = datetime.strptime(row[fecha_idx], '%Y-%m-%d')
                    if timezone.is_naive(dt): dt = timezone.make_aware(dt)
                    res.creado_en = dt
                    res.save()
                except:
                    pass

            for idx, original_idx in enumerate(col_idxs):
                if original_idx < len(row) and row[original_idx].strip():
                    p = preguntas[idx]
                    val = row[original_idx]
                    if p.tipo in ['number', 'scale']:
                        try:
                            RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p,
                                                             valor_numerico=int(float(val)))
                        except:
                            pass
                    else:
                        RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p, valor_texto=val)
            count += 1
        messages.success(request, f"Creada con {count} respuestas.")
        return redirect('surveys:detail', pk=encuesta.pk)
    except Exception as e:
        messages.error(request, f"Error: {e}")
        return redirect('surveys:list')


def responder(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk)
    if encuesta.estado != 'active': return HttpResponse("Inactiva", 403)
    if request.method == 'POST':
        res = RespuestaEncuesta.objects.create(encuesta=encuesta, anonima=True)
        for p in encuesta.preguntas.all():
            k = f'pregunta_{p.id}'
            val = request.POST.get(k)
            if p.tipo == 'text' and val:
                RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p, valor_texto=val)
            elif p.tipo in ['number', 'scale'] and val:
                RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p, valor_numerico=int(val))
            elif p.tipo == 'single' and val:
                RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p, opcion_id=val)
            elif p.tipo == 'multi':
                for v in request.POST.getlist(k): RespuestaPregunta.objects.create(respuesta_encuesta=res, pregunta=p,
                                                                                   opcion_id=v)
        return redirect('surveys:thanks')
    return render(request, 'surveys/fill.html', {'encuesta': encuesta})


def thanks_view(request): return render(request, 'surveys/thanks.html')


@login_required
def export_csv(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig',
                            headers={'Content-Disposition': f'attachment; filename="{encuesta.id}.csv"'})
    writer = csv.writer(response)
    qs = encuesta.preguntas.all().order_by('orden')
    writer.writerow(['ID', 'Fecha'] + [p.texto for p in qs])
    for r in encuesta.respuestas.all().prefetch_related('respuestas_pregunta'):
        row = [r.id, r.creado_en]
        rmap = {rp.pregunta_id: rp for rp in r.respuestas_pregunta.all()}
        for p in qs:
            rp = rmap.get(p.id)
            row.append(rp.valor_texto if rp and rp.valor_texto else (
                rp.valor_numerico if rp and rp.valor_numerico is not None else (
                    rp.opcion.texto if rp and rp.opcion else '')))
        writer.writerow(row)
    return response


# ============================================================
# VISTA DE RESULTADOS (CORREGIDA PARA JSON)
# ============================================================

@login_required
def resultados(request, pk):
    encuesta = get_object_or_404(Encuesta, pk=pk, creador=request.user)
    respuestas_orm = RespuestaEncuesta.objects.filter(encuesta=encuesta).prefetch_related(
        "respuestas_pregunta__pregunta", "respuestas_pregunta__opcion")
    total_respuestas = respuestas_orm.count()

    if total_respuestas == 0:
        return render(request, "surveys/results.html", {
            "encuesta": encuesta, "metrics": {"total_respuestas": 0}, "total_respuestas": 0,
            "nps_score": None, "trend_data": json.dumps({"labels": [], "data": []}),
            "analysis_data_json": "[]", "page_name": "surveys"  # Importante mandar JSON vacío
        })

    # 1. DataFrame y Tendencia
    df = build_responses_df(encuesta, respuestas_orm)
    trend_data = compute_trend_data(respuestas_orm)

    # 2. NPS
    pregunta_nps = encuesta.preguntas.filter(tipo="scale").first()
    nps_score, nps_estado = (None, "N/A")
    if pregunta_nps:
        qs_nps = RespuestaPregunta.objects.filter(pregunta=pregunta_nps, valor_numerico__isnull=False)
        nps_score, nps_estado = calcular_nps(qs_nps)

    # 3. Visualizaciones avanzadas (Heatmap/Crosstab)
    heatmap_image, crosstab_html = None, None
    if not df.empty:
        try:
            heatmap_image = generar_heatmap_correlacion(df)
        except:
            pass
        try:
            cols = [c for c in df.columns if c != "Fecha"]
            if len(cols) >= 2: crosstab_html = pd.crosstab(df[cols[0]], df[cols[1]]).to_html(
                classes="table table-sm table-bordered mb-0", border=0)
        except:
            pass

    # 4. Análisis por Pregunta
    analysis_data = []
    for pregunta in encuesta.preguntas.all().order_by("orden"):
        col_name = pregunta.texto
        if col_name not in df.columns: continue
        series = df[col_name].dropna()
        if series.empty: continue

        item = {
            "id": pregunta.id, "texto": pregunta.texto, "tipo": pregunta.tipo,
            "pregunta_tipo": pregunta.get_tipo_display(),
            "stats": {}, "chart_labels": [], "chart_data": [], "respuestas": [], "insight": ""
        }

        if pregunta.tipo == "text":
            words, bigrams = analizar_texto_avanzado([{"valor_texto": str(t)} for t in series])
            item["stats"]["top_words"] = words
            item["respuestas"] = [{"valor_texto": str(t)} for t in series.head(5)]
            item[
                "insight"] = f"Tema principal: <strong>'{bigrams[0][0] if bigrams else (words[0][0] if words else 'Variado')}'</strong>"

        elif pregunta.tipo in ["number", "scale"]:
            s_num = pd.to_numeric(series, errors="coerce").dropna()
            if not s_num.empty:
                desc = s_num.describe()
                item["stats"] = {"promedio": desc["mean"], "minimo": desc["min"], "maximo": desc["max"],
                                 "mediana": s_num.median()}
                if pregunta.tipo == "scale": item["stats"]["nps"] = nps_score if pregunta == pregunta_nps else None

                item[
                    "insight"] = f"Promedio: <strong>{desc['mean']:.1f}</strong> (Mín: {desc['min']:.0f} - Máx: {desc['max']:.0f})"

                counts = s_num.value_counts().sort_index()
                if pregunta.tipo == "scale":
                    limit_max = 5 if s_num.max() <= 5 else 10
                    limit_min = 0 if s_num.min() == 0 else 1
                    counts = counts.reindex(range(limit_min, limit_max + 1), fill_value=0)

                item["chart_labels"] = [str(i) for i in counts.index]
                item["chart_data"] = counts.values.tolist()

        elif pregunta.tipo in ["single", "multi"]:
            if pregunta.tipo == "multi":
                opts = []
                for v in series: opts.extend([x.strip() for x in str(v).split(',')])
                counts = pd.Series(opts).value_counts()
            else:
                counts = series.value_counts()

            if not counts.empty:
                item["stats"]["moda"] = f"{counts.index[0]} ({counts.iloc[0]})"
                item["insight"] = f"Opción ganadora: <strong>{counts.index[0]}</strong>"
                item["chart_labels"] = counts.index.tolist()
                item["chart_data"] = counts.values.tolist()

        analysis_data.append(item)

    try:
        last_date = respuestas_orm.latest("creado_en").creado_en
    except:
        last_date = None

    metrics = {"total_respuestas": total_respuestas, "nps": nps_score, "ultima_respuesta": last_date}

    # --- CORRECCIÓN CLAVE: Serializar analysis_data para JS ---
    analysis_data_json = json.dumps(analysis_data, cls=DjangoJSONEncoder)

    context = {
        "encuesta": encuesta, "metrics": metrics, "total_respuestas": total_respuestas,
        "nps_score": nps_score, "nps_estado": nps_estado,
        "trend_data": json.dumps(trend_data),
        "analysis_data": analysis_data,  # Para usar en el HTML (Django template)
        "analysis_data_json": analysis_data_json,  # Para usar en el JS (Chart.js)
        "heatmap_image": heatmap_image, "crosstab_html": crosstab_html,
        "top_insights": analysis_data[:3],  # Top 3 para resumen
        "page_name": "surveys",
    }
    return render(request, "surveys/results.html", context)