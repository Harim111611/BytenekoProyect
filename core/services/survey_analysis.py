"""Ultra-optimized survey analysis helpers."""

import logging
import re
import time
import unicodedata
from collections import Counter, defaultdict

from django.core.cache import cache
from django.db import connection

from core.utils.logging_utils import log_performance

logger = logging.getLogger(__name__)

CACHE_TIMEOUT_ANALYSIS = 3600  # 1 hour

STOP_WORDS = {
    'este', 'esta', 'estas', 'estos', 'para', 'pero', 'porque', 'pues', 'solo', 'sobre', 'todo', 'tantos',
    'todas', 'todos', 'tras', 'ademas', 'cada', 'como', 'cuando', 'donde', 'entonces', 'entre', 'hasta',
    'luego', 'mientras', 'mucho', 'poco', 'segun', 'siempre', 'tambien', 'tanto', 'teneis', 'tengo',
    'tenia', 'tenian', 'tenias', 'tenido', 'tenidos', 'teniendo', 'tenemos', 'tener', 'tienes',
    'que', 'con', 'los', 'las', 'una', 'uno', 'unos', 'unas', 'del', 'por', 'estoy', 'estan', 'estas',
    'usted', 'ustedes', 'ellos', 'ellas', 'ser', 'son', 'era', 'eran', 'fue', 'fueron', 'muy', 'mas', 'menos',
    'muchas', 'muchos', 'nuestro', 'nuestra', 'nuestros', 'nuestras', 'sus', 'sino', 'sin', 'sobre',
    'the', 'and', 'this', 'that', 'with', 'from', 'have', 'been', 'were', 'will', 'would', 'there', 'their',
    'which', 'about', 'more', 'some', 'than', 'into', 'your', 'just', 'them', 'they', 'very', 'much', 'many',
    'here', 'only', 'even', 'what', 'when', 'where', 'while', 'also', 'back', 'down', 'over', 'such', 'most',
    'other', 'really', 'still', 'well', 'mucho', 'algo', 'algun', 'ningun', 'ninguna', 'asi', 'aunque', 'desde'
}

AGE_KEYWORDS = [
    'edad', 'age', 'anos', 'years old', 'years-old', 'cuantos anos', 'cuantos years', 'age range', 'rango de edad'
]
AGE_OPTION_HINTS = ['anos', 'edad', 'years']
AGE_RANGE_REGEX = re.compile(r'\b\d{1,2}\s*(?:-|a|to|–)\s*\d{1,2}\b')


class SurveyAnalysisService:
    """Ultra-optimized survey analysis service using raw SQL."""

    @staticmethod
    @log_performance(threshold_ms=2000)
    def get_analysis_data(survey, responses_queryset, include_charts=True, cache_key=None, use_base_filter=True):
        """Return enriched analysis for a survey using raw SQL and lightweight post-processing."""

        timings = {}

        questions = list(survey.questions.prefetch_related('options').order_by('order'))

        date_keywords = ['fecha', 'date', 'created', 'creado', 'timestamp', 'hora', 'time', 'nacimiento', 'birth']
        identifier_keywords = [
            'nombre', 'name', 'apellido', 'last name', 'first name', 'full name',
            'correo', 'email', 'mail', 'e-mail',
            'telefono', 'tel', 'phone', 'celular', 'mobile', 'whatsapp',
            'id', 'identificacion', 'identification', 'documento', 'dni', 'curp', 'rfc', 'cedula', 'passport', 'folio',
            'numero de cliente', 'customer id'
        ]

        def normalize_text(text):
            if not text:
                return ''
            normalized = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
            return normalized.lower()

        def contains_keyword(normalized_text, keyword):
            keyword = keyword.lower()
            if ' ' in keyword:
                return keyword in normalized_text
            return re.search(r'\b' + re.escape(keyword) + r'\b', normalized_text) is not None

        skipped_questions = []
        filtered_questions = []

        for question in questions:
            normalized_text = normalize_text(question.text or '')

            skip_reason = None
            if any(contains_keyword(normalized_text, kw) for kw in date_keywords):
                skip_reason = 'Campo temporal/fecha'
            elif any(contains_keyword(normalized_text, kw) for kw in identifier_keywords):
                skip_reason = 'Dato personal o identificador'

            is_age_question = False
            if question.type in {'number', 'scale', 'single'}:
                if any(contains_keyword(normalized_text, kw) for kw in AGE_KEYWORDS):
                    is_age_question = True
                elif question.type == 'single':
                    option_texts = [normalize_text(opt.text or '') for opt in question.options.all()]
                    joined_options = ' '.join(option_texts)
                    if any(hint in joined_options for hint in AGE_OPTION_HINTS) or AGE_RANGE_REGEX.search(joined_options):
                        is_age_question = True
            setattr(question, 'is_age_demographic', is_age_question)

            if skip_reason:
                skipped_questions.append({'id': question.id, 'text': question.text, 'reason': skip_reason})
                continue

            filtered_questions.append(question)

        if not filtered_questions:
            empty_result = {
                'analysis_data': [],
                'nps_data': {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0, 'chart_image': None},
                'heatmap_image': None,
                'kpi_prom_satisfaccion': 0,
                'ignored_questions': skipped_questions,
            }
            if cache_key:
                cache.set(cache_key, empty_result, CACHE_TIMEOUT_ANALYSIS)
            return empty_result

        start_count = time.time()
        if use_base_filter:
            response_ids = None
            response_count = responses_queryset.count()
        else:
            response_ids = list(responses_queryset.values_list('id', flat=True)[:50000])
            response_count = len(response_ids)
        timings['count_responses'] = round((time.time() - start_count) * 1000)

        if response_count == 0:
            analysis_data = [_create_empty_question_item(q, idx) for idx, q in enumerate(filtered_questions, 1)]
            empty_result = {
                'analysis_data': analysis_data,
                'nps_data': {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0, 'chart_image': None},
                'heatmap_image': None,
                'kpi_prom_satisfaccion': 0,
                'ignored_questions': skipped_questions,
            }
            if cache_key:
                cache.set(cache_key, empty_result, CACHE_TIMEOUT_ANALYSIS)
            return empty_result

        numeric_question_ids = [q.id for q in filtered_questions if q.type in {'scale', 'number'}]
        choice_question_ids = [q.id for q in filtered_questions if q.type == 'single' or getattr(q, 'is_age_demographic', False)]
        multi_question_ids = [q.id for q in filtered_questions if q.type == 'multi']
        text_question_ids = [q.id for q in filtered_questions if q.type == 'text']

        numeric_stats = {}
        numeric_distributions = defaultdict(list)
        choice_distributions = defaultdict(list)
        multi_distributions = defaultdict(list)
        multi_combinations = defaultdict(Counter)
        text_counts = {}
        text_samples = defaultdict(list)
        text_responses_all = defaultdict(list)
        age_question_info = {}

        sql_start = time.time()
        with connection.cursor() as cursor:
            if numeric_question_ids:
                ids = ','.join(map(str, numeric_question_ids))
                cursor.execute(
                    f"""
                    SELECT question_id,
                           COUNT(*) as cnt,
                           AVG(numeric_value) as avg_val,
                           MIN(numeric_value) as min_val,
                           MAX(numeric_value) as max_val
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids})
                      AND numeric_value IS NOT NULL
                    GROUP BY question_id
                    """
                )
                for question_id, count, avg_val, min_val, max_val in cursor.fetchall():
                    numeric_stats[question_id] = {
                        'question_id': question_id,
                        'count': count,
                        'avg': float(avg_val) if avg_val is not None else 0,
                        'min_val': float(min_val) if min_val is not None else 0,
                        'max_val': float(max_val) if max_val is not None else 0,
                    }
            timings['q1_numeric_stats'] = round((time.time() - sql_start) * 1000)

            start = time.time()
            if numeric_question_ids:
                ids = ','.join(map(str, numeric_question_ids))
                cursor.execute(
                    f"""
                    SELECT question_id, numeric_value, COUNT(*) as cnt
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids})
                      AND numeric_value IS NOT NULL
                    GROUP BY question_id, numeric_value
                    ORDER BY question_id, numeric_value
                    """
                )
                for question_id, numeric_value, count in cursor.fetchall():
                    numeric_distributions[question_id].append({'value': float(numeric_value), 'count': count})
            timings['q2_numeric_dist'] = round((time.time() - start) * 1000)

            start = time.time()
            if choice_question_ids:
                ids = ','.join(map(str, choice_question_ids))
                cursor.execute(
                    f"""
                    SELECT qr.question_id, ao.text, COUNT(*) as cnt
                    FROM surveys_questionresponse qr
                    JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id
                    WHERE qr.question_id IN ({ids})
                      AND qr.selected_option_id IS NOT NULL
                    GROUP BY qr.question_id, ao.text
                    ORDER BY qr.question_id, cnt DESC
                    """
                )
                for question_id, option_text, count in cursor.fetchall():
                    choice_distributions[question_id].append({'option': option_text, 'count': count})
            timings['q3_choice_dist'] = round((time.time() - start) * 1000)

            start = time.time()
            if multi_question_ids:
                ids = ','.join(map(str, multi_question_ids))
                cursor.execute(
                    f"""
                    SELECT qr.question_id, ao.text, COUNT(*) as cnt
                    FROM surveys_questionresponse qr
                    JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id
                    WHERE qr.question_id IN ({ids})
                      AND qr.selected_option_id IS NOT NULL
                    GROUP BY qr.question_id, ao.text
                    ORDER BY qr.question_id, cnt DESC
                    """
                )
                for question_id, option_text, count in cursor.fetchall():
                    multi_distributions[question_id].append({'option': option_text, 'count': count})
                    multi_combinations[question_id][option_text] += count

                cursor.execute(
                    f"""
                    SELECT question_id, text_value
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids})
                      AND text_value IS NOT NULL
                      AND text_value != ''
                      AND selected_option_id IS NULL
                    """
                )
                raw_text_responses = defaultdict(list)
                for question_id, text_value in cursor.fetchall():
                    raw_text_responses[question_id].append(text_value)

                for question_id, responses in raw_text_responses.items():
                    option_counts = defaultdict(int)
                    for response in responses:
                        options = [opt.strip() for opt in re.split(r'[;,]', response) if opt.strip()]
                        if options:
                            combo = ', '.join(sorted(options))
                            multi_combinations[question_id][combo] += 1
                        for option in options:
                            option_counts[option] += 1

                    for option, count in option_counts.items():
                        multi_distributions[question_id].append({'option': option, 'count': count})
            timings['q4_multi_dist'] = round((time.time() - start) * 1000)

            start = time.time()
            if text_question_ids:
                ids = ','.join(map(str, text_question_ids))
                cursor.execute(
                    f"""
                    SELECT question_id, text_value
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids})
                      AND text_value IS NOT NULL
                      AND text_value != ''
                    """
                )
                for question_id, text_value in cursor.fetchall():
                    text_responses_all[question_id].append(text_value)
                    if len(text_samples[question_id]) < 5:
                        text_samples[question_id].append(text_value)

                for question_id, responses in text_responses_all.items():
                    text_counts[question_id] = len(responses)
            timings['q5_text_analysis'] = round((time.time() - start) * 1000)

        timings['total_sql'] = round((time.time() - sql_start) * 1000)
        logger.warning("TIMING DEBUG: %s", timings)

        for question in filtered_questions:
            if getattr(question, 'is_age_demographic', False):
                dist = numeric_distributions.get(question.id, [])
                if not dist:
                    continue

                counts_by_age = {}
                for entry in dist:
                    age_value = int(round(entry['value']))
                    if age_value < 0 or age_value > 120:
                        continue
                    counts_by_age[age_value] = counts_by_age.get(age_value, 0) + entry['count']

                if not counts_by_age:
                    continue

                unique_age_count = len(counts_by_age)
                min_age = min(counts_by_age)
                max_age = max(counts_by_age)
                total_responses_age = sum(counts_by_age.values())

                cumulative = 0
                median_age = None
                halfway = total_responses_age / 2
                for age in sorted(counts_by_age):
                    cumulative += counts_by_age[age]
                    if cumulative >= halfway:
                        median_age = age
                        break

                if unique_age_count <= 8 or (max_age - min_age) <= 6:
                    chart_distribution = [
                        {'option': f"{age}", 'count': counts_by_age[age]} for age in sorted(counts_by_age)
                    ]
                else:
                    standard_bins = [
                        (0, 17, 'Menores de 18'),
                        (18, 24, '18-24'),
                        (25, 34, '25-34'),
                        (35, 44, '35-44'),
                        (45, 54, '45-54'),
                        (55, 64, '55-64'),
                        (65, 120, '65+'),
                    ]
                    chart_distribution = []
                    for lower, upper, label in standard_bins:
                        count = sum(counts_by_age.get(age, 0) for age in range(lower, upper + 1))
                        if count > 0:
                            if lower == upper:
                                label = f"{lower}"
                            chart_distribution.append({'option': label, 'count': count})
                    if not chart_distribution:
                        chart_distribution = [
                            {'option': f"{age}", 'count': count} for age, count in sorted(counts_by_age.items())
                        ]

                choice_distributions[question.id] = chart_distribution

                age_question_info[question.id] = {
                    'counts_by_age': counts_by_age,
                    'unique_ages': unique_age_count,
                    'total': total_responses_age,
                    'avg': numeric_stats.get(question.id, {}).get('avg'),
                    'min': min_age,
                    'max': max_age,
                    'median': median_age,
                    'chart_distribution': chart_distribution,
                }

        scale_question_ids = [q.id for q in filtered_questions if q.type == 'scale']
        satisfaction_avg = 0
        if scale_question_ids:
            total_sum = 0
            total_count = 0
            for question_id in scale_question_ids:
                stats = numeric_stats.get(question_id)
                if not stats:
                    continue
                total_sum += (stats['avg'] or 0) * (stats['count'] or 0)
                total_count += stats['count'] or 0
            if total_count > 0:
                satisfaction_avg = total_sum / total_count

        nps_data = {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0, 'chart_image': None}
        if scale_question_ids:
            nps_qid = scale_question_ids[0]
            dist = numeric_distributions.get(nps_qid)
            if dist:
                promoters = sum(entry['count'] for entry in dist if entry['value'] >= 9)
                passives = sum(entry['count'] for entry in dist if 7 <= entry['value'] < 9)
                detractors = sum(entry['count'] for entry in dist if entry['value'] < 7)
                total = promoters + passives + detractors
                if total > 0:
                    nps_score = round(((promoters - detractors) / total) * 100, 1)
                    nps_data = {
                        'score': nps_score,
                        'promoters': round((promoters / total) * 100, 1),
                        'passives': round((passives / total) * 100, 1),
                        'detractors': round((detractors / total) * 100, 1),
                        'chart_image': None,
                    }

        analysis_data = []

        for idx, question in enumerate(filtered_questions, 1):
            item = _create_empty_question_item(question, idx)
            question_id = question.id
            is_age_question = getattr(question, 'is_age_demographic', False)

            if is_age_question:
                age_info = age_question_info.get(question_id, {})
                dist = age_info.get('chart_distribution', [])
                item['tipo_display'] = 'Perfil demográfico'
                if dist:
                    labels = [entry['option'] for entry in dist]
                    data = [entry['count'] for entry in dist]
                    total = age_info.get('total', sum(data)) or 0

                    item['chart_labels'] = labels
                    item['chart_data'] = data
                    item['total_respuestas'] = total
                    item['opciones'] = [
                        {
                            'opcion': labels[pos],
                            'frecuencia': data[pos],
                            'porcentaje': round((data[pos] / total) * 100, 1) if total > 0 else 0,
                        }
                        for pos in range(len(labels))
                    ]
                    item['top_options'] = item['opciones'][:5]

                    ranked = sorted(dist, key=lambda entry: entry['count'], reverse=True)
                    top_entry = ranked[0]
                    top_label = top_entry['option']
                    top_pct = round((top_entry['count'] / total) * 100, 1) if total > 0 else 0
                    top_per_10 = max(1, round(top_pct / 10)) if top_pct > 0 else 0

                    insight_parts = []
                    if top_pct > 0:
                        insight_parts.append(
                            f"👥 <strong>Perfil de edad:</strong> El grupo más numeroso es <strong>{top_label}</strong> "
                            f"({top_pct}% • {top_per_10} de cada 10 personas)."
                        )
                    else:
                        insight_parts.append(
                            f"👥 <strong>Perfil de edad:</strong> El grupo más numeroso es <strong>{top_label}</strong>."
                        )

                    if len(ranked) > 1 and total > 0:
                        second_entry = ranked[1]
                        second_pct = round((second_entry['count'] / total) * 100, 1)
                        if second_pct > 0:
                            insight_parts.append(
                                f"Le sigue <strong>{second_entry['option']}</strong> con {second_pct}% del total."
                            )

                    unique_groups = len(labels)
                    if unique_groups >= 5:
                        insight_parts.append(
                            f"Hay <strong>{unique_groups}</strong> grupos de edad representados, mostrando una audiencia diversa."
                        )
                    elif unique_groups <= 2:
                        insight_parts.append(
                            f"La audiencia es bastante homogénea en edad: solo <strong>{unique_groups}</strong> grupo(s) distintos."
                        )

                    min_age = age_info.get('min')
                    max_age = age_info.get('max')
                    if min_age is not None and max_age is not None and max_age > min_age:
                        insight_parts.append(
                            f"El rango de edades va de <strong>{int(min_age)}</strong> a <strong>{int(max_age)}</strong> años."
                        )

                    avg_age = age_info.get('avg')
                    median_age = age_info.get('median')
                    stats_bits = []
                    if avg_age is not None:
                        stats_bits.append(f"promedio <strong>{avg_age:.1f}</strong>")
                    if median_age is not None:
                        stats_bits.append(f"mediana <strong>{int(round(median_age))}</strong>")
                    if stats_bits:
                        insight_parts.append("Datos clave: " + ", ".join(stats_bits) + " años.")

                    item['insight'] = " ".join(insight_parts)
                else:
                    item['insight'] = 'No hay suficientes datos de edad aún.'

                analysis_data.append(item)
                continue

            if question.type in {'number', 'scale'} and question_id in numeric_stats:
                stats = numeric_stats[question_id]
                val_avg = stats['avg'] or 0
                val_min = stats['min_val'] or 0
                val_max = stats['max_val'] or 10

                item['total_respuestas'] = stats['count'] or 0
                item['avg'] = val_avg
                item['estadisticas'] = {
                    'minimo': val_min,
                    'maximo': val_max,
                    'promedio': round(val_avg, 2),
                    'mediana': round(val_avg, 2),
                }

                scale_cap = 5 if val_max <= 5 else (10 if val_max <= 10 else int(val_max))
                item['scale_cap'] = scale_cap

                if scale_cap == 5:
                    item['tipo_display'] = 'Escala 1-5'
                elif scale_cap > 10:
                    item['tipo_display'] = 'Valor Numérico'

                normalized = (val_avg / scale_cap) * 10 if scale_cap > 0 else 0

                if normalized >= 8.5:
                    sentiment = 'Excelente'
                    recommendation = 'Resultados sobresalientes que demuestran un alto nivel de satisfacción.'
                    visual_metaphor = 'Piensa en esto como si <strong>9 de cada 10</strong> personas estuvieran muy contentas.'
                elif normalized >= 7:
                    sentiment = 'Bueno'
                    recommendation = 'Resultados positivos, aunque hay oportunidades de mejora.'
                    visual_metaphor = 'Es como si <strong>7 de cada 10</strong> personas estuvieran satisfechas.'
                elif normalized >= 5:
                    sentiment = 'Regular'
                    recommendation = 'Nivel aceptable, pero requiere atención para mejorar la experiencia.'
                    visual_metaphor = 'Equivale a que <strong>la mitad</strong> esté conforme y <strong>la otra mitad</strong> no tanto.'
                else:
                    sentiment = 'Crítico'
                    recommendation = 'Resultados preocupantes que necesitan acción inmediata.'
                    visual_metaphor = 'Se parece a que <strong>7 de cada 10</strong> personas estuvieran insatisfechas.'

                high_thr = max(1, int(round(scale_cap * 0.8)))
                mid_thr = max(1, int(round(scale_cap * 0.6)))

                dist_data = numeric_distributions.get(question_id, [])
                total_responses = sum(entry['count'] for entry in dist_data)
                distribution_text = 'No hay suficientes respuestas todavía.'
                context_msg = ''
                mode_text = ''

                if total_responses > 0:
                    high_count = sum(entry['count'] for entry in dist_data if int(entry['value']) >= high_thr)
                    mid_count = sum(entry['count'] for entry in dist_data if mid_thr <= int(entry['value']) < high_thr)
                    low_count = sum(entry['count'] for entry in dist_data if int(entry['value']) < mid_thr)

                    high_pct = round((high_count / total_responses) * 100)
                    mid_pct = round((mid_count / total_responses) * 100)
                    low_pct = round((low_count / total_responses) * 100)

                    distribution_parts = []
                    if high_pct > 0:
                        high_per_10 = max(1, round(high_pct / 10))
                        if high_per_10 >= 8:
                            distribution_parts.append('<strong>Casi todos</strong> dieron calificaciones altas')
                        elif high_per_10 >= 5:
                            distribution_parts.append('<strong>Más de la mitad</strong> calificó con valores altos')
                        else:
                            distribution_parts.append('<strong>Algunos</strong> dieron calificaciones altas')

                    if mid_pct > 0:
                        if mid_pct >= 30:
                            distribution_parts.append('<strong>Una buena parte</strong> se quedó en el medio')
                        else:
                            distribution_parts.append('<strong>Unos pocos</strong> calificaron regular')

                    if low_pct > 0:
                        low_per_10 = max(1, round(low_pct / 10))
                        if low_per_10 >= 5:
                            distribution_parts.append('<strong>Muchos</strong> dieron calificaciones bajas')
                        elif low_per_10 >= 3:
                            distribution_parts.append('<strong>Algunos</strong> no quedaron satisfechos')
                        else:
                            distribution_parts.append('<strong>Pocos</strong> calificaron bajo')

                    if distribution_parts:
                        distribution_text = ', '.join(distribution_parts) + '.'
                    else:
                        distribution_text = 'La distribución está bastante equilibrada.'

                    if high_pct >= 70:
                        context_msg = ' <strong>En resumen:</strong> La gran mayoría está feliz con esto.'
                    elif low_pct >= 40:
                        context_msg = ' <strong>En resumen:</strong> Hay bastante gente descontenta, esto necesita mejoras urgentes.'
                    elif abs(high_pct - low_pct) < 15:
                        context_msg = ' <strong>En resumen:</strong> Las opiniones están divididas, unos contentos y otros no.'

                    most_common = max(dist_data, key=lambda entry: entry['count']) if dist_data else None
                    if most_common:
                        most_common_val = int(most_common['value'])
                        most_common_pct = round((most_common['count'] / total_responses) * 100)
                        if most_common_pct >= 30:
                            mode_text = (
                                f"<br><br><strong>La calificación más repetida es {most_common_val}</strong>"
                                f" (la eligieron {most_common_pct} de cada 100 personas)."
                            )

                item['insight'] = (
                    f"<strong>{sentiment}</strong>: El promedio es <strong>{val_avg:.1f}</strong> sobre {scale_cap}. "
                    f"{visual_metaphor}"
                    f"<br><br>{distribution_text}{context_msg}{mode_text}"
                    f"<br><br><em>{recommendation}</em>"
                )

                if question_id in numeric_distributions:
                    dist = numeric_distributions[question_id]
                    item['chart_labels'] = [str(int(entry['value'])) for entry in dist]
                    item['chart_data'] = [entry['count'] for entry in dist]

            elif question.type == 'single' and question_id in choice_distributions:
                dist = choice_distributions[question_id][:15]
                total = sum(entry['count'] for entry in dist)

                item['total_respuestas'] = total
                labels = [entry['option'] or 'Sin respuesta' for entry in dist]
                data = [entry['count'] for entry in dist]

                item['chart_labels'] = labels
                item['chart_data'] = data
                item['opciones'] = [
                    {
                        'opcion': labels[pos],
                        'frecuencia': data[pos],
                        'porcentaje': round((data[pos] / total) * 100, 1) if total > 0 else 0,
                    }
                    for pos in range(len(labels))
                ]
                item['top_options'] = item['opciones'][:5]

                if labels and data and total > 0:
                    top_val = data[0]
                    top_label = labels[0]
                    top_pct = round((top_val / total) * 100, 1)
                    top_per_10 = round(top_pct / 10)

                    insight = ''
                    context_details = []

                    if len(labels) > 1:
                        second_val = data[1]
                        second_label = labels[1]
                        second_pct = round((second_val / total) * 100, 1)
                        second_per_10 = round(second_pct / 10)
                        diff = top_pct - second_pct

                        if top_pct > 50:
                            insight = (
                                f"<strong>'{top_label}'</strong> domina: <strong>más de la mitad</strong> de las personas la eligió ({top_pct}%)."
                            )
                            context_details.append(
                                f"Si tuvieras un grupo de 10 personas, <strong>{top_per_10 if top_per_10 <= 10 else 'casi todas'}</strong> elegirían esta opción."
                            )
                        elif diff < 5:
                            insight = f"Empate: <strong>'{top_label}'</strong> y <strong>'{second_label}'</strong> están prácticamente igual."
                            context_details.append(
                                f"En un grupo de 10 personas, <strong>{top_per_10}</strong> elegirían '{top_label}' y <strong>{second_per_10}</strong> elegirían '{second_label}'."
                            )
                        elif diff > 20:
                            insight = f"<strong>'{top_label}'</strong> es la clara ganadora con {top_pct}%."
                            context_details.append(
                                f"Le saca ventaja a <strong>'{second_label}'</strong> ({second_pct}%) por {diff:.0f} puntos. "
                                f"En un grupo de 10 personas, <strong>{top_per_10}</strong> elegirían la primera y solo <strong>{second_per_10}</strong> la segunda."
                            )
                        else:
                            insight = f"<strong>'{top_label}'</strong> es la favorita con {top_pct}%."
                            context_details.append(
                                f"Le sigue <strong>'{second_label}'</strong> con {second_pct}%. De cada 10 personas, "
                                f"<strong>{top_per_10}</strong> prefieren la primera y <strong>{second_per_10}</strong> la segunda."
                            )

                        if len(labels) > 2:
                            third_label = labels[2]
                            third_pct = round((data[2] / total) * 100, 1)
                            third_per_10 = round(third_pct / 10)
                            if third_pct >= 10:
                                context_details.append(
                                    f"En tercer lugar, <strong>'{third_label}'</strong> alcanza el {third_pct}% (<strong>{third_per_10} de cada 10</strong>)."
                                )

                        top_three_total = sum(round((data[pos] / total) * 100, 1) for pos in range(min(3, len(data))))
                        if top_three_total >= 80 and len(labels) > 3:
                            context_details.append(
                                f"<strong>8 de cada 10</strong> personas eligieron una de estas 3 opciones principales. El resto se distribuye entre otras {len(labels) - 3} opciones."
                            )
                        elif len(labels) >= 5:
                            context_details.append(
                                f"Las respuestas están repartidas entre {len(labels)} opciones, mostrando diversidad de opiniones."
                            )
                    else:
                        insight = f"<strong>Todos</strong> eligieron <strong>'{top_label}'</strong> ({top_pct}%)."
                        context_details.append('Unanimidad total: todas las personas dieron la misma respuesta.')

                    full_insight = insight
                    if context_details:
                        full_insight += '<br><br>' + ' '.join(context_details)
                    item['insight'] = full_insight

            elif question.type == 'multi' and question_id in multi_distributions:
                dist = multi_distributions[question_id][:15]
                total = sum(entry['count'] for entry in dist)

                item['total_respuestas'] = total
                labels = [entry['option'] or 'Sin respuesta' for entry in dist]
                data = [entry['count'] for entry in dist]

                item['chart_labels'] = labels
                item['chart_data'] = data
                item['opciones'] = [
                    {
                        'opcion': labels[pos],
                        'frecuencia': data[pos],
                        'porcentaje': round((data[pos] / total) * 100, 1) if total > 0 else 0,
                    }
                    for pos in range(len(labels))
                ]
                item['top_options'] = item['opciones'][:5]

                if labels and data and total > 0:
                    top_label = labels[0]
                    top_pct = round((data[0] / total) * 100, 1)
                    top_per_10 = round(top_pct / 10)

                    insight_parts = [
                        f"<strong>'{top_label}'</strong> es la opción más popular: la eligieron <strong>{top_per_10} de cada 10</strong> personas ({top_pct}%)."
                    ]

                    if len(labels) > 1:
                        second_label = labels[1]
                        second_pct = round((data[1] / total) * 100, 1)
                        second_per_10 = round(second_pct / 10)
                        snippet = (
                            f"También destacan <strong>'{second_label}'</strong> ({second_per_10} de cada 10, {second_pct}%)"
                        )
                        if len(labels) > 2:
                            third_label = labels[2]
                            third_pct = round((data[2] / total) * 100, 1)
                            third_per_10 = round(third_pct / 10)
                            snippet += f" y <strong>'{third_label}'</strong> ({third_per_10} de cada 10, {third_pct}%)."
                        else:
                            snippet += '.'
                        insight_parts.append(snippet)

                    if len(labels) >= 5:
                        insight_parts.append(
                            f"<br><br>Las personas eligieron entre {len(labels)} opciones diferentes. Hay mucha variedad de gustos."
                        )
                    elif len(labels) <= 2:
                        insight_parts.append(
                            f"<br><br>Solo hay {len(labels)} opciones y la gente se concentra en ellas."
                        )

                    combo_found = False
                    if question_id in multi_combinations:
                        top_combos = multi_combinations[question_id].most_common(5)
                        real_combos = [(combo, count) for combo, count in top_combos if ',' in combo and count > 1]
                        if real_combos:
                            top_combo, top_combo_count = real_combos[0]
                            combo_per_10 = round((top_combo_count / total) * 10) if total > 0 else 0
                            insight_parts.append(
                                f"<br><br><strong>Combinación más común:</strong> <strong>{combo_per_10} de cada 10</strong> personas ({top_combo_count} en total) "
                                f"eligieron exactamente estas opciones juntas: <em>'{top_combo}'</em>."
                            )
                            combo_found = True
                            if len(real_combos) > 1:
                                insight_parts.append(
                                    f" También se encontraron otras {len(real_combos) - 1} combinaciones populares."
                                )
                    if not combo_found:
                        insight_parts.append('<br><br>La mayoría elige opciones individuales en lugar de combinarlas.')

                    item['insight'] = ' '.join(insight_parts)

            elif question.type == 'text':
                count = text_counts.get(question_id, 0)
                item['total_respuestas'] = count
                item['samples_texto'] = text_samples.get(question_id, [])

                if count > 0:
                    insight_parts = [f"Se recibieron <strong>{count} respuestas</strong> escritas a mano."]

                    texts = text_responses_all.get(question_id, [])
                    if texts:
                        all_text = ' '.join(texts).lower()
                        words = re.findall(r'\w+', all_text)
                        filtered_words = [word for word in words if len(word) > 3 and word not in STOP_WORDS]

                        if filtered_words:
                            top_words_counts = Counter(filtered_words).most_common(10)
                            item['top_words'] = [
                                {'palabra': word, 'frecuencia': count_word} for word, count_word in top_words_counts
                            ]

                            if len(filtered_words) > 1:
                                bigrams = zip(filtered_words, filtered_words[1:])
                                bigram_counts = Counter(bigrams).most_common(5)
                                item['top_bigrams'] = [
                                    {'frase': f"{first} {second}", 'frecuencia': count_pair}
                                    for (first, second), count_pair in bigram_counts
                                ]

                            if top_words_counts:
                                top_word, top_count = top_words_counts[0]

                                if count >= 10:
                                    per_10 = round((top_count / count) * 10)
                                    if per_10 >= 7:
                                        freq_description = f"<strong>Casi todas las respuestas</strong> ({per_10} de cada 10)"
                                    elif per_10 >= 4:
                                        freq_description = f"<strong>Muchas respuestas</strong> ({per_10} de cada 10)"
                                    else:
                                        freq_description = f"<strong>Algunas respuestas</strong> ({per_10} de cada 10)"
                                else:
                                    freq_description = f"<strong>{top_count} respuestas</strong>"

                                insight_parts.append(
                                    f"<br><br><strong>Palabra clave principal:</strong> '{top_word}'. {freq_description} mencionan esta palabra."
                                )

                                if len(top_words_counts) >= 3:
                                    other_words = ', '.join([f"'{word}'" for word, _ in top_words_counts[1:4]])
                                    insight_parts.append(f" Otras palabras importantes: {other_words}.")

                                positive_words = {
                                    'bien', 'bueno', 'excelente', 'genial', 'perfecto', 'feliz', 'satisfecho',
                                    'good', 'great', 'excellent', 'amazing', 'happy'
                                }
                                negative_words = {
                                    'mal', 'malo', 'terrible', 'pesimo', 'error', 'problema', 'fallo',
                                    'bad', 'poor', 'awful', 'problem', 'issue', 'complaint'
                                }

                                positive_count = sum(1 for word in filtered_words if word in positive_words)
                                negative_count = sum(1 for word in filtered_words if word in negative_words)

                                if positive_count > negative_count * 1.5:
                                    insight_parts.append(
                                        f"<br><br><strong>Tono general: Positivo.</strong> La gente usó {positive_count} palabras alegres vs solo {negative_count} negativas."
                                    )
                                elif negative_count > positive_count * 1.5:
                                    insight_parts.append(
                                        f"<br><br><strong>Tono general: Negativo.</strong> Hay {negative_count} palabras de queja vs solo {positive_count} positivas. Algo no está gustando."
                                    )
                                else:
                                    insight_parts.append(
                                        f"<br><br><strong>Tono general: Mixto.</strong> Hay opiniones tanto positivas como negativas mezcladas."
                                    )

                            avg_length = sum(len(text.split()) for text in texts) / len(texts)
                            if avg_length > 20:
                                insight_parts.append(
                                    f"<br><br>Las respuestas son <strong>largas y detalladas</strong> (promedio: {int(avg_length)} palabras cada una). La gente se tomó tiempo para explicar."
                                )
                            elif avg_length < 5:
                                insight_parts.append(
                                    f"<br><br>Las respuestas son <strong>cortas</strong> (promedio: {int(avg_length)} palabras). Respuestas rápidas."
                                )

                    item['insight'] = ''.join(insight_parts)

            analysis_data.append(item)

        final_data = {
            'analysis_data': analysis_data,
            'nps_data': nps_data,
            'heatmap_image': None,
            'kpi_prom_satisfaccion': satisfaction_avg,
            'ignored_questions': skipped_questions,
        }

        if cache_key:
            cache.set(cache_key, final_data, CACHE_TIMEOUT_ANALYSIS)

        return final_data


def _create_empty_question_item(question, order):
    """Return an empty analysis structure for a question."""
    return {
        'id': question.id,
        'order': order,
        'text': question.text,
        'type': question.type,
        'tipo_display': question.get_type_display(),
        'insight': '',
        'chart_image': None,
        'chart_data': [],
        'chart_labels': [],
        'total_respuestas': 0,
        'estadisticas': None,
        'opciones': [],
        'samples_texto': [],
        'top_options': [],
        'avg': None,
        'scale_cap': None,
    }


# Legacy imports for compatibility
from core.services.analysis_service import (
    QuestionAnalyzer,
    NPSCalculator,
    DataFrameBuilder,
)
