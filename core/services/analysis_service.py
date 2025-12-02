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
        """
        Analiza preguntas numéricas / de escala y genera un análisis narrativo
        pensado para personas no técnicas.
        """
        question_responses = QuestionResponse.objects.filter(
            question=question,
            survey_response__in=responses_queryset
        )

        values_qs = question_responses.filter(numeric_value__isnull=False)
        values_list = list(values_qs.values_list('numeric_value', flat=True))

        result = {
            'total_respuestas': question_responses.count(),
            'estadisticas': None,
            'avg': None,
            'scale_cap': None,
            'chart_image': None,
            'chart_data': None,
            'insight': '',
        }

        # Sin datos numéricos → se muestra mensaje simple
        if not values_list:
            result['insight'] = (
                "Aún no hay suficientes respuestas numéricas para dar una lectura confiable "
                "de esta pregunta."
            )
            return result

        # 1) Estadísticos básicos
        val_min = min(values_list)
        val_max = max(values_list)
        val_avg = sum(values_list) / len(values_list)
        val_med = statistics.median(values_list)
        val_stdev = statistics.stdev(values_list) if len(values_list) > 1 else 0

        result['estadisticas'] = {
            'minimo': val_min,
            'maximo': val_max,
            'promedio': val_avg,
            'mediana': val_med,
        }
        result['avg'] = val_avg

        # 2) Contexto del tipo de pregunta
        subject = ContextHelper.get_subject_label(
            getattr(question.survey, "category", "")
        )

        text_lower = question.text.lower()
        negative_metrics = [
            'tiempo', 'espera', 'demora', 'tardanza',
            'errores', 'fallos', 'problemas', 'quejas', 'costo',
        ]
        demographic_metrics = [
            'edad', 'años', 'antigüedad', 'hijos', 'personas',
            'veces', 'cantidad', 'ingresos',
        ]

        # intent = qué significa “alto” en esta pregunta
        if any(k in text_lower for k in demographic_metrics):
            intent = "demographic"       # sólo describimos, no juzgamos
        elif any(k in text_lower for k in negative_metrics):
            intent = "negative_metric"    # alto = malo (mucho tiempo de espera, muchos errores…)
        else:
            intent = "satisfaction"       # alto = bueno (satisfacción, recomendación, calidad…)

        # 3) Detectar tope de escala automáticamente
        if val_max <= 5:
            scale_cap = 5
        elif val_max <= 10:
            scale_cap = 10
        else:
            scale_cap = int(val_max)

        result['scale_cap'] = scale_cap

        # 4) Clasificación del promedio (Excelente / Bueno / Regular / Crítico)
        # Normalizamos a escala 0–10 para comparar siempre igual
        normalized = (val_avg / scale_cap) * 10 if scale_cap > 0 else val_avg

        if intent == "negative_metric":
            # Aquí un valor BAJO es bueno
            if normalized <= 3:
                sentiment = "Muy bueno (bajo)"
                emoji = "✅"
                val_interpretation = (
                    "los valores son bajos, lo cual es deseable en este indicador "
                    "(menos problemas o menos tiempo)."
                )
            elif normalized <= 6:
                sentiment = "Aceptable"
                emoji = "🟡"
                val_interpretation = (
                    "el resultado es intermedio: no es crítico, "
                    "pero hay espacio para reducir aún más estos valores."
                )
            else:
                sentiment = "Crítico (alto)"
                emoji = "🔴"
                val_interpretation = (
                    "los valores son altos; vale la pena revisar qué está generando "
                    "tantos incidentes o tiempos elevados."
                )
        elif intent == "demographic":
            # No hablamos de “bueno/malo”, sólo describimos
            sentiment = "Distribución descriptiva"
            emoji = "📊"
            val_interpretation = (
                "este valor sirve como referencia para entender el perfil típico "
                f"de los {subject} que respondieron."
            )
        else:
            # Satisfacción / recomendación / calidad → alto es bueno
            if normalized >= 8.5:
                sentiment = "Excelente"
                emoji = "🌟"
                val_interpretation = (
                    "refleja una experiencia muy positiva; la mayoría está realmente satisfecha."
                )
            elif normalized >= 7:
                sentiment = "Bueno"
                emoji = "✅"
                val_interpretation = (
                    "muestra que la mayoría está satisfecha, aunque todavía hay margen de mejora."
                )
            elif normalized >= 5:
                sentiment = "Regular"
                emoji = "⚠️"
                val_interpretation = (
                    "indica una experiencia mixta: hay aspectos que funcionan y otros que generan dudas."
                )
            else:
                sentiment = "Crítico"
                emoji = "🛑"
                val_interpretation = (
                    "señala una experiencia negativa; conviene analizar qué está fallando."
                )

        # 5) Cómo se reparten las respuestas (alto / medio / bajo)
        total_vals = len(values_list)

        high_thr = max(1, int(round(scale_cap * 0.8)))
        mid_thr = max(1, int(round(scale_cap * 0.6)))

        high_count = sum(1 for v in values_list if v >= high_thr)
        mid_count = sum(1 for v in values_list if mid_thr <= v < high_thr)
        low_count = total_vals - high_count - mid_count

        def pct(n):
            return round((n / total_vals) * 100) if total_vals else 0

        if intent == "negative_metric":
            # Para métricas negativas, lo “bueno” son los valores bajos
            good_pct = pct(low_count)
            mid_pct = pct(mid_count)
            bad_pct = pct(high_count)
            distribution_text = (
                "En este indicador un número bajo es mejor. Aproximadamente "
                f"<strong>{good_pct}%</strong> de las respuestas están en la zona baja "
                f"(mejor escenario), <strong>{mid_pct}%</strong> en un punto intermedio y "
                f"<strong>{bad_pct}%</strong> en valores altos donde conviene investigar qué ocurrió."
            )
        else:
            high_pct = pct(high_count)
            mid_pct = pct(mid_count)
            low_pct = pct(low_count)
            distribution_text = (
                f"La mayoría de las respuestas se concentran en notas "
                f"altas ({high_thr} o más) con <strong>{high_pct}%</strong>, "
                f"un <strong>{mid_pct}%</strong> se queda en valores medios y sólo "
                f"<strong>{low_pct}%</strong> cae en la parte baja de la escala."
            )

        # 6) Grado de consenso (dispersión)
        if total_vals <= 1:
            consensus_text = (
                "Por ahora sólo hay una respuesta registrada, así que esta lectura "
                "debe tomarse como preliminar."
            )
        else:
            if val_stdev > (scale_cap / 3.5):
                consensus_text = (
                    "Las opiniones están muy divididas: hay personas que puntúan muy alto "
                    "y otras que dan calificaciones bajas."
                )
            elif val_stdev < (scale_cap / 6) and val_stdev > 0:
                consensus_text = (
                    f"Casi todos los {subject} responden de forma parecida; "
                    "hay un fuerte consenso."
                )
            else:
                consensus_text = "Hay una variación normal entre las respuestas."

        # 7) Construir texto final para la tarjeta (item.insight) con explicación narrativa
        # Insight narrativo extendido con desglose explícito
        if intent == "negative_metric":
            insight_narrative = (
                f"{emoji} <strong>{sentiment}</strong>: El promedio es <strong>{val_avg:.1f}</strong> sobre {scale_cap}. "
                f"Esto significa que {val_interpretation} "
                f"De todas las respuestas, el <strong>{good_pct}%</strong> está en la zona baja (lo ideal en este indicador), "
                f"el <strong>{mid_pct}%</strong> en valores intermedios y el <strong>{bad_pct}%</strong> en la zona alta, donde conviene investigar. "
                f"{consensus_text}"
            )
        else:
            insight_narrative = (
                f"{emoji} <strong>{sentiment}</strong>: El promedio es <strong>{val_avg:.1f}</strong> sobre {scale_cap}. "
                f"Esto significa que {val_interpretation} "
                f"El <strong>{high_pct}%</strong> de los participantes eligió valores altos ({high_thr} o más), "
                f"<strong>{mid_pct}%</strong> se quedó en valores medios y solo <strong>{low_pct}%</strong> dio calificaciones bajas. "
                f"{consensus_text}"
            )
        result['insight'] = insight_narrative

        # 8) Datos para la gráfica
        if include_charts:
            counts = collections.Counter(values_list)

            max_range = scale_cap if scale_cap <= 10 else int(val_max) + 1

            if max_range > 20:
                # Para escalas muy largas, usamos sólo los valores presentes
                sorted_keys = sorted(counts.keys())
                labels = [str(k) for k in sorted_keys]
                data = [counts[k] for k in sorted_keys]
            else:
                labels = [str(x) for x in range(1, max_range + 1)]
                data = [counts.get(x, 0) for x in range(1, max_range + 1)]

            result['chart_data'] = {'labels': labels, 'data': data}
            result['chart_image'] = ChartGenerator.generate_vertical_bar_chart(
                labels, data, "Distribución de respuestas"
            )

        return result

class NPSCalculator:
    """Net Promoter Score Calculator."""

    @staticmethod
    def calculate_nps(scale_question, responses_queryset, include_chart=True):
        if not scale_question:
            return {
                'score': None,
                'breakdown_chart': None,
                'insight': '',
                'promotores': 0,
                'pasivos': 0,
                'detractores': 0,
                'pct_promotores': 0,
                'pct_pasivos': 0,
                'pct_detractores': 0,
            }

        nps_qs = QuestionResponse.objects.filter(
            question=scale_question,
            survey_response__in=responses_queryset,
            numeric_value__isnull=False,
        )

        total = nps_qs.count()
        if total == 0:
            return {
                'score': None,
                'breakdown_chart': None,
                'insight': '',
                'promotores': 0,
                'pasivos': 0,
                'detractores': 0,
                'pct_promotores': 0,
                'pct_pasivos': 0,
                'pct_detractores': 0,
            }

        promoters = nps_qs.filter(numeric_value__gte=9).count()
        passives = nps_qs.filter(numeric_value__in=[7, 8]).count()
        detractors = nps_qs.filter(numeric_value__lte=6).count()

        pct_promoters = (promoters / total) * 100
        pct_passives = (passives / total) * 100
        pct_detractors = (detractors / total) * 100

        nps_score = round(pct_promoters - pct_detractors, 1)

        # Clasificación de salud de marca
        if nps_score >= 70:
            category = "Excelente"
            emoji = "🌟"
            summary = (
                "tienes muchos más promotores que detractores; "
                "la mayoría de las personas recomendaría tu servicio."
            )
        elif nps_score >= 50:
            category = "Muy bueno"
            emoji = "✅"
            summary = (
                "la balanza es claramente positiva; todavía hay margen para convertir "
                "más clientes neutros en promotores."
            )
        elif nps_score >= 0:
            category = "Aceptable"
            emoji = "⚠️"
            summary = (
                "hay casi tantos promotores como detractores; es clave entender qué "
                "se podría mejorar para que la experiencia sea más consistente."
            )
        else:
            category = "Crítico"
            emoji = "🛑"
            summary = (
                "hay más detractores que promotores; conviene revisar los puntos de "
                "contacto principales y escuchar a quienes tuvieron mala experiencia."
            )

        subject = ContextHelper.get_subject_label(
            getattr(scale_question.survey, "category", "")
        )

        insight_nps = (
            f"{emoji} <strong>Salud de marca: {category}</strong> "
            f"(NPS = <strong>{nps_score}</strong>). "
            f"De cada 100 {subject}, aproximadamente "
            f"<strong>{pct_promoters:.1f}%</strong> son promotores (9–10), "
            f"<strong>{pct_passives:.1f}%</strong> son neutros (7–8) y "
            f"<strong>{pct_detractors:.1f}%</strong> son detractores (0–6). "
            f"{summary}"
        )

        breakdown_chart = None
        if include_chart:
            breakdown_chart = ChartGenerator.generate_nps_chart(
                promoters, passives, detractors
            )

        return {
            'score': nps_score,
            'breakdown_chart': breakdown_chart,
            'insight': insight_nps,
            'promotores': promoters,
            'pasivos': passives,
            'detractores': detractors,
            'pct_promotores': round(pct_promoters, 1),
            'pct_pasivos': round(pct_passives, 1),
            'pct_detractores': round(pct_detractors, 1),
        }
