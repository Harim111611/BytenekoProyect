"""
Service for survey data analysis.
Contains all processing logic and advanced statistical analysis with natural narrative generation.
"""
import re
import collections
import statistics
import pandas as pd
from django.db.models import Count, Avg
from surveys.models import QuestionResponse
from core.utils.charts import ChartGenerator


class ContextHelper:
    """Helper to determine the semantic context of the survey."""
    
    @staticmethod
    def get_subject_label(category):
        """Returns the appropriate term for respondents based on category."""
        cat = (category or "").lower()
        if any(x in cat for x in ['salud', 'hospital', 'clínica', 'medicina']):
            return "pacientes"
        elif any(x in cat for x in ['educación', 'universidad', 'escuela', 'curso']):
            return "estudiantes"
        elif any(x in cat for x in ['rrhh', 'recursos humanos', 'clima', 'empleado', 'laboral']):
            return "colaboradores"
        elif any(x in cat for x in ['hotel', 'turismo', 'viaje', 'hospitalidad']):
            return "huespedes"
        elif any(x in cat for x in ['restaurante', 'comida', 'gastronomía']):
            return "comensales"
        elif any(x in cat for x in ['tecnología', 'software', 'app', 'saas', 'web']):
            return "usuarios"
        elif any(x in cat for x in ['venta', 'retail', 'comercio', 'tienda']):
            return "clientes"
        return "encuestados"  # Default


class TextAnalyzer:
    """Text analyzer for open-ended responses."""
    
    SPANISH_STOPWORDS = {
        'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'se', 'del', 'las', 
        'un', 'por', 'con', 'no', 'una', 'su', 'para', 'es', 'al', 'lo', 
        'como', 'mas', 'o', 'sin', 'sobre', 'me', 'mi', 'yo', 'tu', 'te',
        'le', 'si', 'ya', 'ni', 'mismo', 'esta', 'este', 'ese', 'algo',
        'donde', 'cual', 'quien', 'cuando', 'hay', 'ser', 'estar', 'tener',
        'hacer', 'poder', 'dar', 'cada', 'otro', 'tal', 'pero', 'mas', 'muy',
        'son', 'fue', 'era', 'todo', 'nada', 'porque', 'pues'
    }
    
    # Sentiment dictionaries
    POSITIVE_WORDS = {
        'bien', 'bueno', 'buena', 'excelente', 'genial', 'mejor', 'gran', 
        'perfecto', 'correcto', 'fácil', 'facil', 'rápido', 'rapido', 
        'útil', 'util', 'feliz', 'contento', 'satisfecho', 'gracias',
        'eficaz', 'eficiente', 'amable', 'profesional', 'encanta', 'gusta',
        'buenos', 'buenas', 'increíble', 'maravilloso', 'agradable', 'limpio',
        'claridad', 'ayuda', 'solución', 'calidad'
    }
    
    NEGATIVE_WORDS = {
        'mal', 'malo', 'mala', 'pésimo', 'pesimo', 'peor', 'horrible',
        'lento', 'difícil', 'dificil', 'complicado', 'error', 'fallo',
        'problema', 'deficiente', 'inútil', 'inutil', 'caro', 'costoso',
        'tarde', 'demora', 'espera', 'nunca', 'jamás', 'triste', 'enojado',
        'sucio', 'desordenado', 'grosero', 'malo', 'lenta', 'ruido', 'caos',
        'falla', 'nadie', 'falta'
    }
    
    @staticmethod
    def analyze_sentiment(words):
        """Calculates a simple sentiment score."""
        pos_count = sum(1 for w in words if w in TextAnalyzer.POSITIVE_WORDS)
        neg_count = sum(1 for w in words if w in TextAnalyzer.NEGATIVE_WORDS)
        
        total_significant = pos_count + neg_count
        
        if total_significant == 0:
            return "Neutral", "bi-chat-square-text", "secondary", "El tono de los comentarios es mayormente informativo o neutral."
            
        score = (pos_count - neg_count) / total_significant  # Range -1 to 1
        
        if score > 0.2:
            return "Positivo", "bi-emoji-smile-fill", "success", "Predominan las opiniones favorables y palabras de agradecimiento o satisfacción."
        elif score < -0.2:
            return "Negativo", "bi-emoji-frown-fill", "danger", "Se detecta un tono de queja o insatisfacción en varios comentarios."
        else:
            return "Mixto", "bi-emoji-neutral-fill", "warning", "Las opiniones están balanceadas entre aspectos positivos y negativos."

    @staticmethod
    def analyze_text_responses(queryset, max_texts=2000):
        """Analyzes text responses to extract keywords, bigrams, and sentiment."""
        texts = list(queryset.values_list('text_value', flat=True))
        texts = [t for t in texts if t and len(str(t).strip()) > 0]
        
        if not texts:
            return [], [], None
        
        if len(texts) > max_texts:
            texts = texts[:max_texts]
        
        # Text processing
        text_full = " ".join(str(t) for t in texts).lower()
        clean = re.sub(r'[^\wáéíóúüñ\s]', ' ', text_full)
        words = clean.split()
        
        # Filter stopwords
        filtered = [
            w for w in words 
            if w not in TextAnalyzer.SPANISH_STOPWORDS 
            and len(w) >= 3
            and not w.isdigit()
        ]
        
        if not filtered:
            return [], [], None
        
        # Sentiment Analysis
        sentiment_label, sentiment_icon, sentiment_color, description = TextAnalyzer.analyze_sentiment(filtered)
        sentiment_data = {
            'label': sentiment_label,
            'icon': sentiment_icon,
            'color': sentiment_color,
            'description': description
        }
        
        # Bigramas
        bigrams = []
        for i in range(len(filtered) - 1):
            if len(filtered[i]) >= 3 and len(filtered[i + 1]) >= 3:
                bigrams.append(f"{filtered[i]} {filtered[i + 1]}")
        
        word_counter = collections.Counter(filtered)
        bigram_counter = collections.Counter(bigrams)
        
        return (
            word_counter.most_common(5),
            bigram_counter.most_common(3),
            sentiment_data
        )


class DataFrameBuilder:
    """Builder for pandas DataFrames."""
    
    @staticmethod
    def build_responses_dataframe(survey, responses_queryset):
        """Builds a pivoted DataFrame."""
        data = QuestionResponse.objects.filter(
            survey_response__in=responses_queryset
        ).values(
            'survey_response__id',
            'survey_response__created_at',
            'question__text',
            'text_value',
            'numeric_value',
            'selected_option__text'
        )
        
        if not data:
            return pd.DataFrame()
        
        df_raw = pd.DataFrame(list(data))
        if df_raw.empty:
            return pd.DataFrame()
        
        # Combine numeric, option, and text values without downcasting
        df_raw['valor'] = df_raw['numeric_value'].combine_first(
            df_raw['selected_option__text']
        ).combine_first(df_raw['text_value'])
        
        try:
            df = df_raw.pivot_table(
                index='survey_response__id',
                columns='question__text',
                values='valor',
                aggfunc='first'
            )
            return df
        except Exception:
            return pd.DataFrame()


class QuestionAnalyzer:
    """Specific analyzer per question type with advanced context logic."""
    
    @staticmethod
    def analyze_numeric_question(question, responses_queryset, include_charts=True):
        """Analyzes numeric questions with explanatory narrative."""
        question_responses = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset
        )
        
        values_list = list(question_responses.filter(numeric_value__isnull=False).values_list('numeric_value', flat=True))
        
        result = {
            'total_respuestas': question_responses.count(),
            'estadisticas': None,
            'avg': None,
            'scale_cap': None,
            'chart_image': None,
            'chart_data': None,
            'insight': ''
        }
        
        if not values_list:
            return result
        
        # 1. Basic Statistics
        val_min = min(values_list)
        val_max = max(values_list)
        val_avg = sum(values_list) / len(values_list)
        val_med = statistics.median(values_list)
        val_stdev = statistics.stdev(values_list) if len(values_list) > 1 else 0
        
        result['estadisticas'] = {
            'minimo': val_min, 'maximo': val_max, 'promedio': val_avg, 'mediana': val_med
        }
        result['avg'] = val_avg
        
        # 2. Context
        subject = ContextHelper.get_subject_label(question.survey.category)

        # Text analysis for text responses (for samples_texto, top_words, top_bigrams)
        qs_text = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset
        ).exclude(text_value__isnull=True).exclude(text_value__exact="")
        words, bigrams, _ = TextAnalyzer.analyze_text_responses(qs_text)
        result['samples_texto'] = list(qs_text.values_list('text_value', flat=True)[:5])
        result['top_words'] = [{'palabra': w[0], 'frecuencia': w[1]} for w in words]
        result['top_bigrams'] = [{'frase': b[0], 'frecuencia': b[1]} for b in bigrams]
        text_lower = question.text.lower()
        
        negative_metrics = ['tiempo', 'espera', 'demora', 'tardanza', 'errores', 'fallos', 'problemas', 'quejas', 'costo']
        demographic_metrics = ['edad', 'años', 'antigüedad', 'hijos', 'personas', 'veces', 'cantidad', 'ingresos']
        
        intent = "satisfaction"
        if any(k in text_lower for k in demographic_metrics):
            intent = "demographic"
        elif any(k in text_lower for k in negative_metrics):
            intent = "negative_metric"
            
        # 3. Intelligent Scale Detection
        if val_max <= 5:
            scale_cap = 5
        elif val_max <= 10:
            scale_cap = 10
        else:
            scale_cap = int(val_max)
            
        result['scale_cap'] = scale_cap
            
        # 4. Generate Narrative
        if intent == "demographic":
            insight_title = "📊 Perfil Demográfico"
            narrative = (
                f"El promedio registrado es de <strong>{val_avg:.1f}</strong>. "
                f"Esto nos indica que el perfil típico de los {subject} se sitúa alrededor de este valor. "
                f"El rango total va desde {val_min} hasta {val_max}, mostrando la diversidad del grupo."
            )
            result['scale_cap'] = int(val_max) if int(val_max) > 0 else 10
            
        else:
            normalized = (val_avg / scale_cap) * 10 if scale_cap > 0 else 0
            sentiment = ""
            emoji = ""
            val_interpretation = ""
            
            if intent == "negative_metric":
                if normalized <= 3:
                    sentiment, emoji, val_interpretation = "Óptimo (Bajo)", "🟢", "es positivo, indicando baja incidencia."
                elif normalized <= 6:
                    sentiment, emoji, val_interpretation = "Aceptable", "🟡", "está en un rango medio tolerable."
                else:
                    sentiment, emoji, val_interpretation = "Crítico (Alto)", "🔴", "es alarmante, indicando problemas frecuentes."
            else:
                if normalized >= 8:
                    sentiment, emoji, val_interpretation = "Excelente", "🌟", "es sobresaliente, reflejando una experiencia muy positiva."
                elif normalized >= 6:
                    sentiment, emoji, val_interpretation = "Bueno", "✅", "es positivo, aunque con espacio para mejorar."
                elif normalized >= 4:
                    sentiment, emoji, val_interpretation = "Regular", "⚠️", "indica un desempeño regular."
                else:
                    sentiment, emoji, val_interpretation = "Crítico", "🛑", "es deficiente y requiere atención inmediata."

            consensus_text = ""
            if val_stdev > (scale_cap / 3.5):
                consensus_text = f"<strong>Atención:</strong> Las opiniones están <strong>muy divididas</strong>."
            elif val_stdev < (scale_cap / 6) and val_stdev > 0:
                consensus_text = f"Existe un <strong>fuerte consenso</strong> entre los {subject}."
            else:
                consensus_text = "Hay una variabilidad normal en las respuestas."

            insight_title = f"{emoji} Resultado: {sentiment}"
            narrative = (
                f"Evaluado en una escala de 1 a {scale_cap}, el promedio es <strong>{val_avg:.1f}</strong>. "
                f"Este valor {val_interpretation}<br><span class='d-block mt-2'>{consensus_text}</span>"
            )

        result['insight'] = f"<strong>{insight_title}</strong><br><div class='mt-2 mb-2' style='font-size: 0.95em; line-height: 1.4;'>{narrative}</div>"
        
        if include_charts:
            counts = collections.Counter(values_list)
            max_range = scale_cap if scale_cap <= 10 else int(val_max) + 1
            
            if max_range > 20:
                sorted_keys = sorted(counts.keys())
                labels = [str(k) for k in sorted_keys]
                data = [counts[k] for k in sorted_keys]
            else:
                labels = [str(x) for x in range(1, max_range + 1)]
                data = [counts.get(x, 0) for x in range(1, max_range + 1)]
            
            result['chart_data'] = {'labels': labels, 'data': data}
            result['chart_image'] = ChartGenerator.generate_vertical_bar_chart(
                labels, data, "Distribución de Respuestas"
            )
        
        return result
    
    @staticmethod
    def analyze_choice_question(question, responses_queryset, include_charts=True):
        """Analyzes choice questions with explanatory narrative."""
        question_responses = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset
        ).select_related('selected_option')
        
        result = {
            'total_respuestas': question_responses.count(),
            'opciones': [],
            'top_options': [],
            'chart_image': None,
            'chart_data': None,
            'insight': ''
        }
        
        all_vals = []
        for r in question_responses:
            if r.selected_option:
                all_vals.append(r.selected_option.text)
            elif r.text_value:
                val_clean = [x.strip() for x in r.text_value.split(',') if x.strip()]
                all_vals.extend(val_clean)
        
        total_votes = len(all_vals)
        if total_votes == 0:
            result['insight'] = "Sin datos suficientes para generar un análisis."
            return result
        
        counter = collections.Counter(all_vals)
        options_list = []
        for label, count in counter.most_common():
            pct = (count / total_votes) * 100
            options_list.append({
                'text': label, 'label': label, 'count': count, 'percent': pct
            })
        
        result['opciones'] = options_list
        result['top_options'] = counter.most_common(3)
        
        subject = ContextHelper.get_subject_label(question.survey.category)
        
        is_binary = False
        if len(options_list) <= 3:
            labels_set = {op['text'].lower() for op in options_list}
            if labels_set & {'si', 'sí', 'no', 'yes', 'true', 'false'}:
                is_binary = True
        
        if is_binary:
            top_opt = options_list[0]
            narrative = f"Tendencia clara: <strong>{top_opt['percent']:.1f}%</strong> de {subject} eligió <strong>'{top_opt['text']}'</strong>."
            icon, title = "bi-pie-chart-fill text-primary", "Distribución Binaria"
        elif result['top_options']:
            winner, w_count = result['top_options'][0]
            w_pct = (w_count / total_votes) * 100
            title, icon = "Análisis de Preferencias", "bi-bar-chart-line-fill text-primary"
            narrative = f"La opción líder es <strong>{winner}</strong> ({w_pct:.0f}%). "
            
            if len(result['top_options']) > 1:
                second, s_count = result['top_options'][1]
                s_pct = (s_count / total_votes) * 100
                if (w_pct - s_pct) < 10:
                    narrative += f"Competencia reñida con <strong>{second}</strong>."
                    title = "Preferencia Dividida"
                else:
                    narrative += f"Ventaja clara sobre {second}."

        result['insight'] = f"<i class='bi {icon}'></i> <strong>{title}</strong><br><div class='mt-2' style='font-size:0.95em'>{narrative}</div>"
            
        if include_charts and result['opciones']:
            top_10 = result['opciones'][:10]
            labels = [item['text'] for item in top_10]
            data = [item['count'] for item in top_10]
            result['chart_data'] = {'labels': labels, 'data': data}
            # Prefer donut/pie image for choice questions when option count is small (better visual)
            try:
                if len(labels) <= 10:
                    img = ChartGenerator.generate_pie_chart(labels, data, "Frecuencia")
                    if img:
                        result['chart_image'] = img
                    else:
                        result['chart_image'] = ChartGenerator.generate_vertical_bar_chart(labels, data, "Frecuencia")
                else:
                    result['chart_image'] = ChartGenerator.generate_vertical_bar_chart(labels, data, "Frecuencia")
            except Exception:
                # Fallback a barra en caso de error en la generación de dona
                result['chart_image'] = ChartGenerator.generate_vertical_bar_chart(labels, data, "Frecuencia")
        
        return result
    
    @staticmethod
    def analyze_text_question(question, responses_queryset):
        """Analyzes text responses with sentiment detection."""
        text_qs = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset
        ).exclude(text_value__isnull=True).exclude(text_value__exact="")
        
        result = {
            'total_respuestas': text_qs.count(),
            'samples_texto': list(text_qs.values_list('text_value', flat=True)[:5]),
            'insight': '', 'top_words': [], 'top_bigrams': []
        }
        
        words, bigrams, sentiment_data = TextAnalyzer.analyze_text_responses(text_qs)
        subject = ContextHelper.get_subject_label(question.survey.category)
        
        if words:
            result['top_words'] = [{'palabra': w[0], 'frecuencia': w[1]} for w in words]
            result['top_bigrams'] = [{'frase': b[0], 'frecuencia': b[1]} for b in bigrams]
            main_topic = words[0][0]
            insight_html = f"<strong>Tema frecuente:</strong> <span class='badge bg-light text-dark'>{main_topic}</span><br>"
            if sentiment_data:
                insight_html += f"<i class='bi {sentiment_data['icon']} text-{sentiment_data['color']}'></i> <strong>Tono: {sentiment_data['label']}</strong><br>"
            insight_html += f"<small class='text-muted'>Basado en comentarios de {subject}.</small>"
            result['insight'] = insight_html
        else:
            result['insight'] = f"Aún no hay suficientes comentarios de {subject}."
        return result


class NPSCalculator:
    """Net Promoter Score Calculator."""
    
    @staticmethod
    def calculate_nps(scale_question, responses_queryset, include_chart=True):
        if not scale_question: return {'score': None, 'breakdown_chart': None}
        
        nps_qs = QuestionResponse.objects.filter(
            question=scale_question, survey_response__in=responses_queryset, numeric_value__isnull=False
        )
        total = nps_qs.count()
        if total == 0: return {'score': None, 'breakdown_chart': None}
        
        promoters = nps_qs.filter(numeric_value__gte=9).count()
        passives = nps_qs.filter(numeric_value__in=[7, 8]).count()
        detractors = nps_qs.filter(numeric_value__lte=6).count()
        
        nps_score = round(((promoters / total) * 100) - ((detractors / total) * 100), 1)
        
        category = "Excelente" if nps_score >= 50 else "Positivo" if nps_score >= 0 else "Crítico"
        emoji = '<i class="bi bi-star-fill text-warning"></i>' if nps_score >= 50 else '<i class="bi bi-check-circle-fill text-success"></i>' if nps_score >= 0 else '<i class="bi bi-exclamation-triangle-fill text-danger"></i>'
        
        insight_nps = f"{emoji} <strong>Salud de Marca: {category}</strong><br><div class='mt-2' style='font-size:0.9em'>NPS: {nps_score}</div>"
        
        breakdown_chart = None
        if include_chart:
            breakdown_chart = ChartGenerator.generate_nps_chart(promoters, passives, detractors)
        
        pct_promoters = (promoters / total) * 100
        pct_passives = (passives / total) * 100
        pct_detractors = (detractors / total) * 100
        
        return {
            'score': nps_score, 'breakdown_chart': breakdown_chart, 'insight': insight_nps,
            'promotores': promoters, 'pasivos': passives, 'detractores': detractors,
            'pct_promotores': round(pct_promoters, 1),
            'pct_pasivos': round(pct_passives, 1),
            'pct_detractores': round(pct_detractors, 1)
        }