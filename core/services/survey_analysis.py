import logging
import re
import math
import random
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import pandas as pd  # Agregado para el manejo de DataFrames y Heatmaps

from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date

from core.utils.logging_utils import log_performance
from core.utils.charts import ChartGenerator

logger = logging.getLogger(__name__)

CACHE_TIMEOUT_ANALYSIS = 3600  # 1 hora

class NPSCalculator:
    @staticmethod
    def calculate_nps(survey_or_question, responses_queryset, include_chart=True):
        """Calcula NPS desde survey (con .questions) o pregunta directa."""
        # Detectar si es survey o pregunta
        nps_question = None
        if hasattr(survey_or_question, 'questions'):
            # Buscar pregunta NPS en survey
            nps_question = survey_or_question.questions.filter(type__in=['scale', 'number'], text__icontains='recomendar').first()
        elif hasattr(survey_or_question, 'type'):
            # Es pregunta directa
            nps_question = survey_or_question
            
        if not nps_question:
            return {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0, 'chart_image': None}
            
        # Buscar respuestas
        qs = getattr(nps_question, 'questionresponse_set', None)
        if qs is not None:
            qs = qs.filter(survey_response__in=responses_queryset, numeric_value__isnull=False)
        else:
            # Fallback: buscar por modelo global si existe
            from surveys.models import QuestionResponse
            qs = QuestionResponse.objects.filter(question=nps_question, survey_response__in=responses_queryset, numeric_value__isnull=False)
            
        total = qs.count()
        if total == 0:
            return {'score': None, 'promoters': 0, 'passives': 0, 'detractors': 0, 'chart_image': None}
            
        promoters = qs.filter(numeric_value__gte=9).count()
        detractors = qs.filter(numeric_value__lte=6).count()
        passives = total - (promoters + detractors)
        score = ((promoters - detractors) / total) * 100
        
        chart_image = None
        if include_chart and ChartGenerator:
            chart_image = ChartGenerator.generate_donut_chart(
                ['Promotores', 'Pasivos', 'Detractores'],
                [promoters, passives, detractors],
                ['#10B981', '#6B7280', '#EF4444']
            )
            
        return {
            'score': round(score, 1),
            'promoters': promoters,
            'passives': passives,
            'detractors': detractors,
            'total': total,
            'chart_image': chart_image
        }

class AnalysisConstants:
    """Palabras comunes para ignorar en análisis de texto y keywords de fecha."""
    STOP_WORDS = {
        'este', 'esta', 'estas', 'estos', 'para', 'pero', 'porque', 'pues', 'solo', 'sobre', 'todo', 
        'que', 'con', 'los', 'las', 'una', 'uno', 'unos', 'unas', 'del', 'por', 'estoy', 'estan',
        'usted', 'ustedes', 'ellos', 'ellas', 'ser', 'son', 'era', 'eran', 'fue', 'fueron', 'muy', 'mas',
        'the', 'and', 'this', 'that', 'with', 'from', 'have', 'been', 'user_agent', 'browser', 'null', 'nan',
        'gracias', 'hola', 'adios', 'buenos', 'dias', 'tardes', 'noches', 'encuesta', 'respuesta', 'comentario',
        'opinion', 'creo', 'pienso', 'siento', 'considero', 'parece', 'gusta'
    }
    
    DATE_KEYWORDS = {'marca temporal', 'timestamp', 'fecha', 'date', 'hora', 'time', 'momento', 'cuando'}

class SensitiveDataFilter:
    """Filtro de seguridad estricto para PII y demográficos."""
    
    ALLOWED_DEMOGRAPHICS = {
        'area', 'departamento', 'gerencia', 'sector', 'rol', 'cargo', 'puesto', 'unidad', 'equipo',
        'ciudad', 'city', 'location', 'ubicacion', 'sede', 'region', 'provincia', 'pais', 'lugar',
        'edad', 'age', 'rango etario', 'generacion', 'anos', 'años', 'nacimiento', 'cumpleanos',
        'pais', 'country', 'nacionalidad', 'genero', 'sexo', 'identidad', 'orientacion', 'nivel', 'estudios'
    }
    
    PII_KEYWORDS = {
        'nombre', 'name', 'apellido', 'lastname', 'surname', 
        'email', 'correo', 'mail', 
        'telefono', 'phone', 'celular', 'mobile', 
        'rut', 'dni', 'cedula', 'passport', 'id', 'identificacion',
        'direccion', 'address', 'calle', 'domicilio',
        'tarjeta', 'credito', 'banco', 'cuenta', 'cbu'
    }

    REGEX_EMAIL = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    @classmethod
    def analyze_question_metadata(cls, question):
        norm_text = normalize_text(question.text)
        tokens = set(norm_text.split())
        
        if any(k in norm_text for k in ['token', 'user_agent', 'ip_address', 'csrf']):
            return 'META', 'Metadato técnico'

        if not tokens.isdisjoint(cls.PII_KEYWORDS):
            return 'PII', 'Datos personales detectados (Nombre/ID/Contacto)'

        is_demo_model = getattr(question, 'is_demographic', False)
        matches_allowed = not tokens.isdisjoint(cls.ALLOWED_DEMOGRAPHICS)
        
        if is_demo_model or matches_allowed:
            return 'DEMO', 'Perfil Demográfico Autorizado'

        return 'VALID', 'Pregunta de opinión'

    @classmethod
    def sanitize_text_responses(cls, texts):
        cleaned = []
        for text in texts:
            if not text: continue
            text = re.sub(cls.REGEX_EMAIL, '[EMAIL OCULTO]', str(text))
            cleaned.append(text)
        return cleaned

class TimelineEngine:
    """Motor inteligente para reconstruir la evolución temporal (limitado a 30 días)."""
    
    @staticmethod
    def analyze_evolution(survey, responses_queryset, questions):
        # 1) Intentar detectar una pregunta de fecha / marca temporal
        date_question = None
        for q in questions:
            norm_text = normalize_text(q.text)
            if any(k in norm_text for k in AnalysisConstants.DATE_KEYWORDS):
                # Prioriza columnas tipo "Marca temporal", "Timestamp", etc.
                if 'marca temporal' in norm_text or 'timestamp' in norm_text:
                    date_question = q
                    break
                # Si es algo genérico como "Fecha" en las primeras preguntas, también cuenta
                if 'fecha' in norm_text and q.order <= 2:
                    date_question = q
                    break
        
        timeline_data = {}
        source_type = 'SYSTEM'
        warning_msg = None

        # 2) Intentar construir el timeline desde el contenido de la encuesta
        if date_question:
            try:
                raw_dates = list(
                    date_question.questionresponse_set.filter(
                        survey_response__in=responses_queryset
                    )
                    .exclude(text_value='')
                    .values_list('text_value', flat=True)
                )
                
                parsed_dates = TimelineEngine._parse_dates_bulk(raw_dates)
                if parsed_dates:
                    timeline_data = TimelineEngine._aggregate_by_day(parsed_dates)
                    source_type = 'CONTENT'
                else:
                    warning_msg = (
                        f"La columna '{date_question.text}' tiene un formato "
                        f"de fecha difícil de interpretar. Se usará la fecha de sistema."
                    )
            except Exception as e:
                logger.error(f"Error timeline (contenido): {e}")

        # 3) Fallback: usar created_at de las respuestas
        if not timeline_data:
            dates = list(responses_queryset.values_list('created_at', flat=True))
            timeline_data = TimelineEngine._aggregate_by_day(dates)

            # Heurística: detectar carga masiva (todas las respuestas en pocos minutos)
            if len(dates) > 10:
                timestamps = [d.timestamp() for d in dates if d]
                if timestamps and (max(timestamps) - min(timestamps)) < 300:
                    warning_msg = (
                        "⚠️ Importación masiva detectada: la línea de tiempo refleja la fecha de carga, "
                        "no necesariamente la fecha real de respuesta."
                    )

        # 4) Si aun así no hay datos, regresar estructura vacía coherente
        if not timeline_data:
            return {
                'labels': [],
                'data': [],
                'source': 'NONE',
                'warning': warning_msg,
                'question_used': None,
            }

        # 5) Ordenar fechas y adaptar rango dinámicamente según los datos disponibles
        sorted_dates = sorted(timeline_data.keys())

        # Si hay fechas, mostrar todo el rango disponible
        labels = [d.strftime('%d/%m/%Y') for d in sorted_dates]
        data = [timeline_data[d] for d in sorted_dates]

        return {
            'labels': labels,
            'data': data,
            'source': source_type,
            'warning': warning_msg,
            'question_used': (
                date_question.text if date_question and source_type == 'CONTENT'
                else 'Sistema'
            ),
        }

    @staticmethod
    def _parse_dates_bulk(raw_values):
        """
        Intenta interpretar una lista de strings como fechas, soportando formatos comunes
        de Google Forms / Excel / CSV.
        """
        valid_dates = []
        formats = [
            '%Y/%m/%d %I:%M:%S %p', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d',
            '%d/%m/%Y %H:%M:%S', '%d/%m/%Y',
            '%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y',
        ]

        for val in raw_values:
            if not val:
                continue
            val_str = str(val).strip()

            # Normalizar ciertas variantes frecuentes
            val_str = val_str.replace('p. m.', 'PM').replace('a. m.', 'AM')
            val_str = val_str.replace('p.m.', 'PM').replace('a.m.', 'AM')
            val_str = re.sub(r'\s+GMT[+-]\d+$', '', val_str)

            dt = parse_datetime(val_str) or parse_date(val_str)
            if not dt or not hasattr(dt, 'year'):
                for fmt in formats:
                    try:
                        dt = datetime.strptime(val_str, fmt)
                        break
                    except ValueError:
                        continue

            if dt:
                if not isinstance(dt, datetime):
                    dt = datetime(dt.year, dt.month, dt.day)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
                valid_dates.append(dt)

        return valid_dates

    @staticmethod
    def _aggregate_by_day(date_objects):
        counts = defaultdict(int)
        for dt in date_objects:
            if dt:
                counts[dt.date()] += 1
        return counts


class DemographicInsightEngine:
    """
    MOTOR DE CONTEXTO "PROFESSIONAL NEUTRAL" (V5.0)
    Genera diagnósticos con tono de consultoría: claro, objetivo y versátil.
    """
    
    DEMO_CONTEXTS = {
        'GENDER': {'genero', 'sexo', 'hombre', 'mujer', 'identidad'},
        'LOCATION': {'ciudad', 'pais', 'ubicacion', 'sede', 'region', 'provincia', 'location', 'city', 'donde'},
        'ROLE': {'area', 'departamento', 'gerencia', 'sector', 'cargo', 'rol', 'puesto', 'trabajas'},
        'AGE': {'edad', 'age', 'rango', 'etario', 'nacimiento', 'anos', 'años', 'tienes'},
        'TENURE': {'antiguedad', 'tiempo', 'tenure', 'ingreso', 'empresa', 'llevas'}
    }

    # PLANTILLAS CATEGÓRICAS (Tono Consultor)
    TEMPLATES_CATEGORICAL = {
        'GENDER': {
            'DOMINANT': [
                "Existe una **brecha representativa** clara: el segmento **{top1}** concentra la mayoría de la muestra.",
                "La distribución no es paritaria, observándose una predominancia significativa del grupo **{top1}**.",
                "El perfil demográfico muestra un sesgo hacia **{top1}**, lo cual debe considerarse al segmentar resultados."
            ],
            'BALANCED': [
                "La muestra presenta **paridad estadística**, con una distribución equitativa entre **{top1}** y **{top2}**.",
                "Se observa un balance saludable en la representación de género, sin sesgos dominantes.",
                "La participación es equilibrada, permitiendo un análisis comparativo robusto entre grupos."
            ],
            'FRAGMENTED': [
                "Se registra diversidad en la identidad de los participantes, sin un grupo hegemónico.",
                "La composición de la muestra es variada, reflejando pluralidad en la participación."
            ]
        },
        'LOCATION': {
            'DOMINANT': [
                "Se identifica una **concentración geográfica** en **{top1}**, que actúa como foco principal de la muestra.",
                "El estudio tiene un fuerte componente local, dado que **{top1}** agrupa la mayoría de las respuestas.",
                "Existe una centralización de la data en **{top1}**, con menor representatividad de otras regiones."
            ],
            'BALANCED': [
                "La cobertura geográfica es **descentralizada**, manteniendo un equilibrio entre **{top1}** y **{top2}**.",
                "La muestra logra representatividad regional, evitando sesgos de ubicación única.",
                "Se observa una distribución territorial balanceada, ideal para análisis comparativos por zona."
            ],
            'FRAGMENTED': [
                "Existe una alta **dispersión territorial**, con participación granular desde múltiples ubicaciones.",
                "El alcance geográfico es amplio y capilar, sin concentraciones masivas en una sola sede."
            ]
        },
        'ROLE': {
            'DOMINANT': [
                "El área de **{top1}** tiene el mayor peso en la muestra, influyendo en la tendencia general.",
                "Se observa una concentración funcional en **{top1}**, lo que sugiere una visión sesgada hacia este departamento.",
                "La representatividad está liderada por **{top1}**, siendo el grupo más participativo."
            ],
            'BALANCED': [
                "Existe una colaboración **transversal**, con participación proporcional entre **{top1}** y **{top2}**.",
                "La estructura de la muestra refleja un buen balance interdepartamental.",
                "No se observan silos de información; la opinión está bien distribuida entre las áreas clave."
            ],
            'FRAGMENTED': [
                "La participación es **multidisciplinaria**, proveniente de una amplia variedad de roles y sectores.",
                "Se registra una alta diversidad funcional, con aportes de múltiples micro-áreas."
            ]
        },
        'GENERAL': { # Fallback para Mercado/Productos/Otros
            'DOMINANT': [
                "**Liderazgo Claro:** La opción **{top1}** se posiciona como la preferida por un margen significativo.",
                "Existe una **tendencia dominante** hacia **{top1}**, que concentra la mayoría de las preferencias.",
                "El consenso es alto: **{top1}** se destaca como la elección principal del grupo."
            ],
            'BALANCED': [
                "**Escenario Competitivo:** Se observa una división equilibrada entre **{top1}** y **{top2}**.",
                "No hay un líder único; la preferencia está polarizada entre las dos opciones principales.",
                "La distribución es homogénea, indicando una competencia cerrada entre las alternativas líderes."
            ],
            'FRAGMENTED': [
                "**Alta Segmentación:** Las preferencias están dispersas, sin una opción que agrupe a la mayoría.",
                "Se observa fragmentación en los resultados, lo que sugiere la necesidad de estrategias de nicho.",
                "El mercado/audiencia muestra gustos diversos, con una "
                "larga cola"
                " de opciones minoritarias."
            ]
        }
    }

    # PLANTILLAS NUMÉRICAS (Edad/Antigüedad + Genérico)
    TEMPLATES_NUMERIC = {
        'AGE': {
            'YOUNG': [ # < 26
                "**Perfil Junior (Gen Z):** El promedio de **{avg:.1f} años** indica una población en etapa de desarrollo temprano. Foco sugerido: Formación y Cultura.",
                "**Talento Emergente:** Con una media de **{avg:.1f}**, predomina una fuerza laboral joven, típicamente adaptable pero en curva de aprendizaje."
            ],
            'EARLY_PRO': [ # 26 - 32
                "**Consolidación Profesional:** El promedio de **{avg:.1f} años** refleja un segmento en crecimiento y alta productividad.",
                "**Perfil en Desarrollo:** La media de **{avg:.1f}** sugiere una audiencia con experiencia inicial sólida y ambición de crecimiento."
            ],
            'MID_CAREER': [ # 33 - 42
                "La edad promedio es de {avg:.1f} años, lo que indica un grupo con experiencia y madurez profesional.",
                "Madurez Profesional: El promedio de {avg:.1f} años indica perfiles expertos, orientados a la estabilidad y eficiencia."
            ],
            'EXPERIENCED': [ # > 42
                "**Seniority Alto:** El promedio de **{avg:.1f} años** revela una población con amplia trayectoria y conocimiento institucional.",
                "**Perfil Experto:** Una media de **{avg:.1f}** sugiere estabilidad, baja rotación y alto valor en consultoría interna o mentoría."
            ]
        },
        'TENURE': {
            'NEWBIE': [ # < 2 años
                "**Fase de Adaptación:** El promedio de **{avg:.1f} años** indica una población de ingreso reciente. Es clave monitorear la experiencia de onboarding.",
                "**Renovación de Talento:** Con **{avg:.1f} años**, la organización atraviesa un ciclo de renovación. Atención a la curva de aprendizaje."
            ],
            'STABLE': [ # 2 - 5 años
                "**Estabilidad Operativa:** El promedio de **{avg:.1f} años** refleja un equipo adaptado y productivo, en etapa de retención.",
                "**Compromiso Sostenido:** Con **{avg:.1f} años**, la población conoce la cultura y procesos, representando la base operativa de la empresa."
            ],
            'VETERAN': [ # > 5 años
                "**Alta Fidelización:** Un promedio de **{avg:.1f} años** denota una fuerte retención y lealtad organizacional.",
                "**Cultura Arraigada:** Con **{avg:.1f} años** de media, este grupo preserva el conocimiento histórico y los valores corporativos."
            ]
        },
        'GENERAL': { # Para cualquier otra pregunta numérica (ej: satisfacción, precio)
            'LOW': [
                "**Indicador Bajo:** El promedio de **{avg:.1f}** se sitúa en el rango inferior. Es necesario investigar las causas de este desempeño.",
                "**Área de Oportunidad:** Con **{avg:.1f}**, el resultado es conservador y sugiere espacio para mejoras significativas."
            ],
            'MID': [
                "**Desempeño Medio:** El promedio de **{avg:.1f}** indica estabilidad, aunque sin alcanzar niveles de excelencia.",
                "**Zona de Consolidación:** Con **{avg:.1f}**, el indicador muestra un comportamiento estándar dentro de lo esperado."
            ],
            'HIGH': [
                "**Desempeño Sobresaliente:** El promedio de **{avg:.1f}** es altamente positivo, situándose en el rango superior de la escala.",
                "**Fortaleza Identificada:** Con **{avg:.1f}**, este indicador representa un activo clave y una ventaja competitiva."
            ]
        }
    }

    @classmethod
    def _detect_demo_context(cls, text):
        norm = normalize_text(text)
        tokens = set(norm.split())
        
        if not tokens.isdisjoint(cls.DEMO_CONTEXTS['AGE']): return 'AGE'
        if not tokens.isdisjoint(cls.DEMO_CONTEXTS['TENURE']): return 'TENURE'
        
        for ctx, keywords in cls.DEMO_CONTEXTS.items():
            if ctx in ['AGE', 'TENURE']: continue
            if not tokens.isdisjoint(keywords): return ctx
        return 'GENERAL'

    @classmethod
    def analyze_categorical(cls, distribution, total_responses, question_text):
        if not distribution or total_responses == 0: return ""
        
        top1 = distribution[0]
        top1_pct = (top1['count'] / total_responses) * 100
        
        top2 = distribution[1] if len(distribution) > 1 else None
        top2_pct = (top2['count'] / total_responses) * 100 if top2 else 0
        
        # Escenarios
        if top1_pct > 55:
            scenario = 'DOMINANT'
            badge_color = 'primary'
            badge_text = 'Tendencia Dominante'
        elif (top1_pct - top2_pct) < 15:
            scenario = 'BALANCED'
            badge_color = 'success'
            badge_text = 'Muestra Balanceada'
        else:
            scenario = 'FRAGMENTED'
            badge_color = 'info'
            badge_text = 'Alta Diversidad'
            
        context = cls._detect_demo_context(question_text)
        if context in ['AGE', 'TENURE']: context = 'GENERAL' # Si es edad categórica, tratamos como general por ahora
        
        # Selección segura de plantilla
        templates_context = cls.TEMPLATES_CATEGORICAL.get(context, cls.TEMPLATES_CATEGORICAL['GENERAL'])
        templates_list = templates_context.get(scenario, cls.TEMPLATES_CATEGORICAL['GENERAL'][scenario])
        
        rng = random.Random(total_responses + len(question_text) + int(top1_pct))
        main_text = rng.choice(templates_list).format(
            top1=top1['option'], 
            top2=top2['option'] if top2 else ''
        )
        
        sub_text = f"La opción principal ({top1['option']}) representa el {top1_pct:.1f}% del total."
        if top2: sub_text += f" Le sigue {top2['option']} con un {top2_pct:.1f}%."

        return f"""
            <div class='analysis-card p-3 border border-{badge_color}-subtle bg-{badge_color}-subtle rounded-3'>
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <span class="badge bg-{badge_color} text-white shadow-sm">{badge_text}</span>
                    <small class="text-body-secondary text-uppercase fw-bold" style="font-size:0.7rem;">{context if context != 'GENERAL' else 'ANÁLISIS'}</small>
                </div>
                <p class='mb-1 text-body-emphasis'>{main_text}</p>
                <p class='mb-0 text-body-secondary small'>{sub_text}</p>
            </div>
        """

    @classmethod
    def analyze_numeric(cls, avg, question_text):
        context = cls._detect_demo_context(question_text)
        rng = random.Random(int(avg * 100) + len(question_text))
        
        label = "Dato Promedio"
        state = "primary"
        
        if context == 'AGE':
            if avg < 26: key = 'YOUNG'
            elif avg < 33: key = 'EARLY_PRO'
            elif avg < 43: key = 'MID_CAREER'
            else: key = 'EXPERIENCED'
            templates = cls.TEMPLATES_NUMERIC['AGE'][key]
            label = "Promedio de Edad"
            
        elif context == 'TENURE':
            if avg < 2: key = 'NEWBIE'
            elif avg < 5: key = 'STABLE'
            else: key = 'VETERAN'
            templates = cls.TEMPLATES_NUMERIC['TENURE'][key]
            label = "Antigüedad"
            state = "success" if key == 'NEWBIE' else "primary"
            
        else:
            # Lógica Genérica para preguntas numéricas de mercado (1-5, 1-10, etc)
            # Asumimos escala 10 o normalizada si es mayor.
            val = avg
            if val > 10: val = val / 10 # Normalización básica heurística
            
            if val < 4: key = 'LOW'; state = "warning"
            elif val < 7: key = 'MID'; state = "primary"
            else: key = 'HIGH'; state = "success"
            
            templates = cls.TEMPLATES_NUMERIC['GENERAL'][key]
            label = "Métrica Clave"

        text = rng.choice(templates).format(avg=avg)

        # Solo el contenido, sin tarjeta extra
        return f"""
            <div class="d-flex justify-content-between align-items-start mb-2">
                <span class="badge bg-{state} text-white shadow-sm">{label}</span>
                <small class="text-body-secondary text-uppercase fw-bold" style="font-size:0.7rem;">INSIGHT</small>
            </div>
            <p class='mb-0 text-body-emphasis'>{text}</p>
        """

class CategoryInsightEngine:
    """Motor de Análisis Categórico General (No demográfico)."""
    
    SCENARIOS = {
        'ABSOLUTE_MAJORITY': {
            'title': 'Líder Indiscutible',
            'color': 'success',
            'templates': [
                "Existe un consenso claro. La opción <strong>{top1}</strong> domina las preferencias con más del 50%.",
                "El resultado es contundente a favor de <strong>{top1}</strong>, superando ampliamente a la competencia.",
                "La mayoría absoluta se inclina por <strong>{top1}</strong>, definiendo una tendencia sólida."
            ]
        },
        'STRONG_LEAD': {
            'title': 'Tendencia Clara',
            'color': 'primary',
            'templates': [
                "Aunque hay diversas opiniones, <strong>{top1}</strong> se destaca como la opción principal.",
                "Se observa una preferencia marcada por <strong>{top1}</strong>, manteniendo una ventaja cómoda.",
                "La balanza se inclina hacia <strong>{top1}</strong>, liderando el grupo de opciones."
            ]
        },
        'TIGHT_RACE': {
            'title': 'Competencia Cerrada',
            'color': 'warning',
            'templates': [
                "La opinión está dividida. <strong>{top1}</strong> lidera por un margen muy estrecho frente a <strong>{top2}</strong>.",
                "Observamos un empate técnico entre las dos opciones principales: <strong>{top1}</strong> y <strong>{top2}</strong>.",
                "No hay un ganador definitivo. La preferencia se disputa palmo a palmo entre los líderes."
            ]
        },
        'FRAGMENTED': {
            'title': 'Alta Dispersión',
            'color': 'secondary',
            'templates': [
                "No existe un consenso. Las preferencias están diluidas entre múltiples opciones.",
                "El mercado muestra gustos muy variados; incluso la opción top (<strong>{top1}</strong>) tiene un peso bajo.",
                "La diversidad de respuestas sugiere un escenario fragmentado sin un líder dominante."
            ]
        }
    }

    @classmethod
    def generate_insight(cls, distribution, total_responses, question_text):
        if not distribution or total_responses == 0:
            return ""

        top1 = distribution[0]
        top1_pct = (top1['count'] / total_responses) * 100
        top2 = distribution[1] if len(distribution) > 1 else None
        top2_pct = (top2['count'] / total_responses) * 100 if top2 else 0
        margin = top1_pct - top2_pct

        if top1_pct >= 50:
            scenario_key = 'ABSOLUTE_MAJORITY'
        elif top1_pct < 35 and margin < 10:
            scenario_key = 'FRAGMENTED'
        elif margin < 15:
            scenario_key = 'TIGHT_RACE'
        else:
            scenario_key = 'STRONG_LEAD'

        scenario = cls.SCENARIOS[scenario_key]
        rng = random.Random(total_responses + int(top1_pct))
        main_text = rng.choice(scenario['templates']).format(
            top1=top1['option'], top2=top2['option'] if top2 else ''
        )

        # Contexto real adicional
        context_lines = [
            f"<b>Total de respuestas:</b> {total_responses}",
            f"<b>Opción más elegida:</b> {top1['option']} ({top1['count']} resp., {top1_pct:.1f}%)",
        ]
        if top2:
            context_lines.append(f"<b>Segunda opción:</b> {top2['option']} ({top2['count']} resp., {top2_pct:.1f}%)")
            context_lines.append(f"<b>Diferencia entre top 1 y 2:</b> {margin:.1f} puntos porcentuales")
        if len(distribution) > 2:
            top3 = distribution[2]
            top3_pct = (top3['count'] / total_responses) * 100
            context_lines.append(f"<b>Tercera opción:</b> {top3['option']} ({top3['count']} resp., {top3_pct:.1f}%)")

        # Si hay dispersión, advierte
        if scenario_key == 'FRAGMENTED' and len(distribution) > 3:
            context_lines.append("<b>Nota:</b> Hay alta dispersión, ninguna opción supera el 35%.")

        context_html = "<br>".join(context_lines)

        strategy = ""
        if scenario_key == 'TIGHT_RACE':
            strategy = "💡 <strong>Nota:</strong> Al existir dos grupos fuertes, las estrategias deben considerar ambas preferencias."
        elif scenario_key == 'FRAGMENTED':
            strategy = "💡 <strong>Nota:</strong> La falta de un líder sugiere oportunidades para soluciones de nicho o personalizadas."
        elif scenario_key == 'ABSOLUTE_MAJORITY':
            strategy = "✨ <strong>Conclusión:</strong> Este resultado permite tomar decisiones con alto grado de certeza."

        return f"""
            <div class='analysis-card p-3 border border-{scenario['color']}-subtle bg-{scenario['color']}-subtle rounded-3'>
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <span class="badge bg-{scenario['color']} text-white shadow-sm">{scenario['title']}</span>
                    <small class="text-body-secondary">{total_responses} resp.</small>
                </div>
                <p class='mb-2 text-body-emphasis'>{main_text}</p>
                <div class='mb-2 small'>{context_html}</div>
                {f"<div class='mt-2 pt-2 border-top border-{scenario['color']}-subtle small text-body-secondary'>{strategy}</div>" if strategy else ""}
            </div>
        """

class TextMiningEngine:
    """Extrae temas clave de textos."""
    @staticmethod
    def extract_topics(texts, top_n=5):
        words = []
        for text in texts:
            clean = normalize_text(text)
            tokens = [w for w in clean.split() if w not in AnalysisConstants.STOP_WORDS and len(w) > 3]
            if tokens:
                words.extend(tokens)
                if len(tokens) > 1:
                    bigrams = [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens)-1)]
                    words.extend(bigrams)
        
        if not words: return "Datos insuficientes para análisis de texto."
        common = Counter(words).most_common(top_n)
        return ", ".join([f"<strong>{c[0]}</strong>" for c in common])

class InsightEngine:
    """Generador de Narrativa Contextual Profunda (Numérica)."""

    CONTEXTS = {
        'TIEMPO': {'tiempo', 'demora', 'espera', 'tardanza', 'rapidez', 'velocidad', 'lento', 'agilidad', 'minutos', 'hora'},
        'ATENCION': {'atencion', 'amabilidad', 'trato', 'personal', 'staff', 'soporte', 'ayuda', 'cortesia', 'ejecutivo'},
        'CALIDAD': {'calidad', 'limpieza', 'estado', 'funcionamiento', 'sabor', 'confort', 'instalaciones', 'ambiente'},
        'PRECIO': {'precio', 'costo', 'valor', 'pagar', 'caro', 'barato', 'economico', 'tarifa'},
        'FACILIDAD': {'facilidad', 'dificultad', 'uso', 'app', 'sistema', 'proceso', 'tramite', 'web', 'accesibilidad'}
    }

    OPENINGS = {
        'EXCELENTE': [
            "Excelente resultado. En este aspecto, el desempeño es sobresaliente.",
            "Posición de liderazgo. Los indicadores aquí son altamente positivos.",
            "Superación de expectativas. La percepción es inmejorable.",
            "Punto fuerte. Estamos marcando un estándar de calidad alto."
        ],
        'BUENO': [
            "Buen desempeño. Tenemos una base sólida con margen de mejora.",
            "Aprobación general. La mayoría evalúa positivamente este aspecto.",
            "Cumplimiento de objetivos. Estamos entregando lo prometido.",
            "Sentimiento positivo. La tendencia es favorable y estable."
        ],
        'REGULAR': [
            "Atención requerida. Detectamos oportunidades de mejora claras.",
            "Desempeño variable. La percepción no es uniforme, hay dudas.",
            "Zona de riesgo. El resultado está por debajo del ideal.",
            "Brecha de expectativa. Hay diferencia entre lo ofrecido y lo esperado."
        ],
        'CRITICO': [
            "Punto crítico. Este indicador requiere acción inmediata.",
            "Alta insatisfacción. Es prioritario revisar este proceso.",
            "Desempeño deficiente. Estamos fallando en un aspecto clave.",
            "Alerta de servicio. Las evaluaciones negativas son predominantes."
        ]
    }

    EVIDENCE_TEMPLATES = {
        'UP': [
            "El promedio de <strong>{avg:.1f}/{scale}</strong> muestra una tendencia de recuperación.",
            "Con un <strong>{avg:.1f}/{scale}</strong>, observamos una curva ascendente positiva."
        ],
        'DOWN': [
            "Aunque el promedio es <strong>{avg:.1f}/{scale}</strong>, la tendencia reciente es a la baja.",
            "Atención: <strong>{avg:.1f}/{scale}</strong>, pero con indicadores de descenso."
        ],
        'STABLE': [
            "El indicador se mantiene estable en <strong>{avg:.1f}/{scale}</strong>.",
            "Observamos un comportamiento constante en <strong>{avg:.1f}/{scale}</strong>."
        ]
    }

    CONSENSUS_TEMPLATES = {
        'HIGH_AGREEMENT': [
            "Existe un alto consenso. La experiencia es consistente para todos.",
            "La variabilidad es mínima, lo que confirma la solidez del dato."
        ],
        'POLARIZED': [
            "Observamos polarización. Hay grupos con opiniones opuestas.",
            "El promedio esconde realidades extremas. Se recomienda segmentar."
        ],
        'NORMAL': [
            "La distribución es estándar, con la mayoría cerca del promedio.",
            "Existe una diversidad de opiniones dentro de lo esperado."
        ]
    }

    STRATEGY_TEMPLATES = {
        'QUICK_WIN': [
            "💡 <strong>Recomendación:</strong> Ajustes menores podrían elevar rápidamente este indicador.",
            "💡 <strong>Oportunidad:</strong> Es un área de mejora accesible con alto retorno."
        ],
        'CRITICAL': [
            "🚨 <strong>Recomendación:</strong> Priorizar recursos para investigar la causa raíz.",
            "🚨 <strong>Acción:</strong> Se sugiere revisión profunda del proceso asociado."
        ],
        'MAINTAIN': [
            "✨ <strong>Recomendación:</strong> Documentar buenas prácticas para replicar el éxito.",
            "✨ <strong>Estrategia:</strong> El reto es mantener la consistencia en este nivel."
        ],
        'WATCH': [
            "👀 <strong>Recomendación:</strong> Mantener bajo monitoreo en el próximo ciclo.",
            "👀 <strong>Seguimiento:</strong> No requiere acción urgente, pero sí vigilancia."
        ]
    }

    @classmethod
    def analyze_metrics(cls, question_text, stats, dist_data, scale_cap, trend_delta=0, question_id=None, previous_context=None):
        rng = random.Random(question_id or stats['avg'])
        context = cls._detect_context(question_text)
        
        avg = stats['avg']
        count = stats['count']
        std_dev = cls._calculate_std_dev(dist_data, avg, count)
        score_10, lower_is_better = cls._normalize_score(avg, scale_cap, context, question_text)
        mood = cls._determine_mood(score_10)

        trend_key = 'STABLE'
        if abs(trend_delta) > 0.05:
            is_good = (trend_delta < 0) if lower_is_better else (trend_delta > 0)
            trend_key = 'UP' if is_good else 'DOWN'

        consensus_key = 'NORMAL'
        if scale_cap > 0:
            if std_dev > (scale_cap * 0.22): consensus_key = 'POLARIZED'
            elif std_dev < (scale_cap * 0.12): consensus_key = 'HIGH_AGREEMENT'

        strategy_key = 'WATCH'
        if mood in ['CRITICO', 'REGULAR']:
            strategy_key = 'CRITICAL' if trend_key == 'DOWN' else 'QUICK_WIN'
        elif mood == 'EXCELENTE':
            strategy_key = 'MAINTAIN'

        line_1 = cls._get_varied_choice(rng, cls.OPENINGS[mood], previous_context.get('line_1') if previous_context else None)
        raw_tmpl_2 = cls._get_varied_choice(rng, cls.EVIDENCE_TEMPLATES[trend_key], previous_context.get('line_2') if previous_context else None)
        line_2 = raw_tmpl_2.format(avg=avg, scale=scale_cap)
        line_3 = cls._get_varied_choice(rng, cls.CONSENSUS_TEMPLATES[consensus_key], previous_context.get('line_3') if previous_context else None)
        line_4 = cls._get_varied_choice(rng, cls.STRATEGY_TEMPLATES[strategy_key], previous_context.get('line_4') if previous_context else None)

        colors = {'EXCELENTE': 'success', 'BUENO': 'primary', 'REGULAR': 'warning', 'CRITICO': 'danger'}
        color = colors.get(mood, 'secondary')

        html = f"""
            <div class='analysis-card p-3 rounded-3 border border-{color}-subtle bg-{color}-subtle'>
                <p class='mb-1 text-body-emphasis fw-medium'>{line_1}</p>
                <p class='mb-1 text-body-secondary'>{line_2}</p>
                <p class='mb-2 text-body-secondary'>{line_3}</p>
                <div class='mt-2 pt-2 border-top border-{color}-subtle text-body-secondary small'>
                    {line_4}
                </div>
            </div>
        """

        return {
            'state': mood, 'insight': html, 
            'score_norm': round(score_10, 1), 
            'context_state': {'line_1': line_1, 'line_2': raw_tmpl_2, 'line_3': line_3, 'line_4': line_4}
        }

    @staticmethod
    def _get_varied_choice(rng, options_list, last_used_value):
        if not options_list: return ""
        choice = rng.choice(options_list)
        if choice == last_used_value and len(options_list) > 1:
            alternatives = [opt for opt in options_list if opt != last_used_value]
            if alternatives: choice = rng.choice(alternatives)
        return choice

    @staticmethod
    def _detect_context(text):
        norm = normalize_text(text)
        tokens = set(norm.split())
        for ctx, keywords in InsightEngine.CONTEXTS.items():
            if not tokens.isdisjoint(keywords): return ctx
        return 'GENERAL'

    @staticmethod
    def _calculate_std_dev(dist_data, avg, count):
        if count <= 1: return 0
        sum_sq = sum(d['count'] * ((d['value'] - avg) ** 2) for d in dist_data)
        return math.sqrt(sum_sq / (count - 1))

    @staticmethod
    def _normalize_score(avg, scale_cap, context, text):
        norm_text = normalize_text(text)
        lower_is_better = False
        if context == 'TIEMPO' and not any(k in norm_text for k in ['satisfaccion', 'calificacion']):
            lower_is_better = True
        elif 'precio' in norm_text and 'caro' in norm_text:
            lower_is_better = True
        
        score = (avg / scale_cap) * 10 if scale_cap > 0 else 0
        final_score = (10 - score) if lower_is_better else score
        return final_score, lower_is_better

    @staticmethod
    def _determine_mood(score):
        if score >= 8.5: return 'EXCELENTE'
        if score >= 7.0: return 'BUENO'
        if score >= 5.0: return 'REGULAR'
        return 'CRITICO'

def normalize_text(text):
    if not text: return ''
    text_str = str(text)
    text_str = text_str.translate(str.maketrans('', '', '¿?¡!_-.[](){}:,"'))
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()

class SurveyAnalysisService:
    """Servicio Maestro Orquestador de análisis de encuestas."""

    @staticmethod
    @log_performance(threshold_ms=2500)
    def get_analysis_data(
        survey,
        responses_queryset,
        include_charts=True,
        cache_key=None,
        use_base_filter=True,
        dark_mode=False,
    ):
        """
        Orquesta el análisis completo:
        - Filtra preguntas analizables (evita PII, timestamps, etc.).
        - Ejecuta agregaciones SQL optimizadas (número, categorías, texto).
        - Genera insights por pregunta usando los motores existentes.
        - Calcula un KPI global y un resumen ejecutivo (meta).
        """
        total_responses = responses_queryset.count()

        if cache_key is None:
            last_id = (
                responses_queryset.order_by('-id')
                .values_list('id', flat=True)
                .first()
                or 0
            )
            cache_key = f"survey_analysis_v15:{survey.id}:{total_responses}:{last_id}"

        cached = cache.get(cache_key)
        if cached:
            return cached

        analysis_data = []
        questions = list(
            survey.questions.prefetch_related('options').order_by('order')
        )

        numeric_stats = {}
        numeric_dist = defaultdict(list)
        trend_stats = {}
        choice_dist = defaultdict(list)
        text_responses = defaultdict(list)
        skipped_log = []

        # Timeline global (ya limitado a 30 días)
        evolution_data = TimelineEngine.analyze_evolution(
            survey, responses_queryset, questions
        )

        # 1. NPS
        nps_data = None
        try:
            nps_data = NPSCalculator.calculate_nps(survey, responses_queryset, include_chart=include_charts)
        except Exception as e:
            logger.error(f"Error calculando NPS: {e}")

        # 2. Heatmap de Correlaciones
        heatmap_image = None
        if include_charts and ChartGenerator:
            try:
                from core.utils.dataframe_builder import DataFrameBuilder
                
                # Construir el DataFrame
                df = DataFrameBuilder.build_responses_dataframe(survey, responses_queryset)
                
                if not df.empty:
                    # OPTIMIZACIÓN: Usar apply con 'coerce' para convertir datos a numéricos
                    # 'coerce' convierte textos no numéricos a NaN, permitiendo recuperar los números válidos.
                    numeric_df = df.apply(pd.to_numeric, errors='coerce')
                    
                    # Filtramos solo las columnas numéricas y eliminamos las que sean todo NaN
                    numeric_df = numeric_df.select_dtypes(include=['number']).dropna(axis=1, how='all')

                    # Para un heatmap (correlación) necesitamos al menos 2 columnas y más de 1 fila
                    if not numeric_df.empty and numeric_df.shape[1] > 1 and numeric_df.shape[0] > 1:
                        heatmap_image = ChartGenerator.generate_heatmap(numeric_df)
                    else:
                        logger.info("Datos insuficientes para generar Heatmap (se requieren al menos 2 variables numéricas).")
                        
            except Exception as e:
                logger.warning(f"No se pudo generar heatmap: {e}")

        # 3) Clasificación de preguntas (VAL/DEMO/PII/META)
        analyzable_q = []
        for q in questions:
            cat, reason = SensitiveDataFilter.analyze_question_metadata(q)
            setattr(q, 'analysis_category', cat)

            if cat in ('PII', 'META'):
                skipped_log.append(
                    {'id': q.id, 'text': q.text, 'reason': reason}
                )
                continue

            analyzable_q.append(q)

        if not analyzable_q:
            return SurveyAnalysisService._build_empty_response(skipped_log)

        # 4) Filtro base SQL usando el queryset ya filtrado (ventana, filtros, etc.)
        try:
            query = responses_queryset.values('id').query
            sql, params = query.get_compiler(
                using=responses_queryset.db
            ).as_sql()
            base_where = f" AND survey_response_id IN ({sql})"
            base_params = list(params)
        except Exception as e:
            logger.error(f"Error construyendo filtro SQL base: {e}")
            return SurveyAnalysisService._build_empty_response(skipped_log)

        # 5) Agregaciones SQL de alto rendimiento
        with connection.cursor() as cursor:
            # A. Numéricos
            num_ids = [q.id for q in analyzable_q if q.type in {'scale', 'number'}]
            if num_ids:
                ids_ph = ','.join(['%s'] * len(num_ids))

                # Stats básicos
                cursor.execute(
                    f"""
                    SELECT question_id, COUNT(*), AVG(numeric_value), MAX(numeric_value)
                    FROM surveys_questionresponse 
                    WHERE question_id IN ({ids_ph})
                      AND numeric_value IS NOT NULL
                      {base_where}
                    GROUP BY question_id
                    """,
                    num_ids + base_params,
                )
                for qid, count, avg, max_val in cursor.fetchall():
                    numeric_stats[qid] = {
                        'count': count,
                        'avg': avg,
                        'max': max_val,
                    }

                # Distribución
                cursor.execute(
                    f"""
                    SELECT question_id, numeric_value, COUNT(*)
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids_ph})
                      AND numeric_value IS NOT NULL
                      {base_where}
                    GROUP BY question_id, numeric_value
                    """,
                    num_ids + base_params,
                )
                for qid, value, count in cursor.fetchall():
                    numeric_dist[qid].append(
                        {'value': value, 'count': count}
                    )

                # Tendencia últimos 50 registros
                cursor.execute(
                    f"""
                    SELECT question_id, AVG(numeric_value)
                    FROM (
                        SELECT question_id,
                               numeric_value,
                               ROW_NUMBER() OVER (
                                   PARTITION BY question_id
                                   ORDER BY id DESC
                               ) AS rn
                        FROM surveys_questionresponse
                        WHERE question_id IN ({ids_ph})
                          AND numeric_value IS NOT NULL
                          {base_where}
                    ) AS recent_data
                    WHERE rn <= 50
                    GROUP BY question_id
                    """,
                    num_ids + base_params,
                )
                for qid, avg_recent in cursor.fetchall():
                    trend_stats[qid] = avg_recent

            # B. Categorías (single / multi)
            cat_ids = [q.id for q in analyzable_q if q.type in {'single', 'multi'}]
            if cat_ids:
                ids_ph = ','.join(['%s'] * len(cat_ids))
                
                # CORRECCIÓN: Nos aseguramos de usar 'survey_response_id' en la cláusula WHERE.
                # Si base_where usa 'id' (de SurveyResponse), lo cambiamos a 'survey_response_id' (de QuestionResponse)
                # Si base_where ya usa 'survey_response_id', el replace no hará daño si no encuentra 'id' aislado.
                fixed_where = base_where
                if 'survey_response_id' not in base_where:
                     fixed_where = base_where.replace('id', 'survey_response_id')

                cursor.execute(
                    f"""
                    SELECT qr.question_id, ao.text, COUNT(*)
                    FROM surveys_questionresponse qr
                    JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id
                    WHERE qr.question_id IN ({ids_ph})
                      {fixed_where}
                    GROUP BY qr.question_id, ao.text
                    """,
                    cat_ids + base_params,
                )
                for qid, label, count in cursor.fetchall():
                    choice_dist[qid].append(
                        {'option': label, 'count': count}
                    )

            # C. Texto abierto
            txt_ids = [q.id for q in analyzable_q if q.type == 'text']
            if txt_ids:
                ids_ph = ','.join(['%s'] * len(txt_ids))
                cursor.execute(
                    f"""
                    SELECT question_id, text_value
                    FROM surveys_questionresponse
                    WHERE question_id IN ({ids_ph})
                      AND text_value <> ''
                      {base_where}
                    """,
                    txt_ids + base_params,
                )
                limit_per_q = 150
                seen = defaultdict(int)
                for qid, text_val in cursor.fetchall():
                    if seen[qid] < limit_per_q:
                        text_responses[qid].append(text_val)
                        seen[qid] += 1

        # 6) Construcción de tarjetas por pregunta
        satisfaction_scores = []
        previous_insight_context = None

        for idx, q in enumerate(analyzable_q, 1):
            item = SurveyAnalysisService._init_item(q, idx)
            qid = q.id
            is_demo = getattr(q, 'analysis_category', 'VALID') == 'DEMO'
            item['is_demographic'] = is_demo

            # --- Numérico ---
            if qid in numeric_stats:
                stats = numeric_stats[qid]
                item.update(stats)
                item['total_respuestas'] = stats['count']

                if not stats['count']:
                    analysis_data.append(item)
                    continue

                scale_cap = 10 if (stats.get('max') or 0) > 5 else 5
                dist = sorted(
                    numeric_dist.get(qid, []), key=lambda d: d['value']
                )
                item['chart_labels'] = [str(int(d['value'])) for d in dist]
                item['chart_data'] = [d['count'] for d in dist]

                trend_avg = trend_stats.get(qid, stats['avg'])
                delta = 0.0
                if stats['avg']:
                    delta = (trend_avg - stats['avg']) / stats['avg']

                if is_demo:
                    # Edad, años en la empresa, etc. en formato numérico
                    demo_insight = DemographicInsightEngine.analyze_numeric(stats['avg'], q.text)
                    context_lines = [
                        f"<b>Total de respuestas:</b> {stats['count']}",
                        f"<b>Promedio:</b> {stats['avg']:.2f}",
                        f"<b>Valor máximo:</b> {stats['max']}"
                    ]
                    context_html = "<br>".join(context_lines)
                    strategy = "💡 <strong>Nota:</strong> Analizar la distribución por segmentos demográficos para identificar patrones relevantes."
                    # Insertar todo dentro de la tarjeta azul (analysis-card)
                    item['insight'] = f"""
                        <div class='analysis-card p-3 border border-primary-subtle bg-primary-subtle rounded-3'>
                            {demo_insight}
                            <div class='mb-2 small'>{context_html}</div>
                            <div class='mt-2 pt-2 border-top border-primary-subtle text-body-secondary small'>{strategy}</div>
                        </div>
                    """
                    previous_insight_context = None
                else:
                    insight_obj = InsightEngine.analyze_metrics(
                        q.text,
                        stats,
                        dist,
                        scale_cap,
                        trend_delta=delta,
                        question_id=qid,
                        previous_context=previous_insight_context,
                    )
                    item['state'] = insight_obj['state']
                    item['insight'] = insight_obj['insight']
                    item['score_norm'] = insight_obj['score_norm']
                    previous_insight_context = insight_obj['context_state']
                    satisfaction_scores.append(stats['avg'])

                if include_charts and item['chart_data']:
                    item['chart_image'] = ChartGenerator.generate_bar_chart(
                        item['chart_labels'],
                        item['chart_data'],
                        "Distribución",
                        dark_mode=dark_mode,
                    )

            # --- Categorías ---
            elif qid in choice_dist:
                dist = sorted(
                    choice_dist[qid], key=lambda d: d['count'], reverse=True
                )
                total = sum(d['count'] for d in dist)
                item['total_respuestas'] = total

                top_n = dist[:10]
                item['chart_labels'] = [d['option'] for d in top_n]
                item['chart_data'] = [d['count'] for d in top_n]
                item['options'] = [
                    {
                        'label': d['option'],
                        'count': d['count'],
                        'percent': round(
                            d['count'] * 100 / total if total else 0, 1
                        ),
                    }
                    for d in dist
                ]

                previous_insight_context = None

                if is_demo:
                    demo_insight = DemographicInsightEngine.analyze_categorical(dist, total, q.text)
                    # Añadir contexto real
                    context_lines = [
                        f"<b>Total de respuestas:</b> {total}",
                        f"<b>Opción más elegida:</b> {dist[0]['option']} ({dist[0]['count']} resp., {dist[0]['count']*100/total:.1f}%)" if dist else ""
                    ]
                    if len(dist) > 1:
                        context_lines.append(f"<b>Segunda opción:</b> {dist[1]['option']} ({dist[1]['count']} resp., {dist[1]['count']*100/total:.1f}%)")
                    context_html = "<br>".join(context_lines)
                    strategy = "💡 <strong>Nota:</strong> Comparar estos resultados con otros segmentos demográficos para obtener insights adicionales."
                    item['insight'] = f"""
                        {demo_insight}
                        <div class='mb-2 small'>{context_html}</div>
                        <div class='mt-2 pt-2 border-top border-success-subtle text-body-secondary small'>{strategy}</div>
                    """
                else:
                    item['insight'] = CategoryInsightEngine.generate_insight(
                        dist, total, q.text
                    )

                if include_charts and item['chart_data']:
                    title = "Perfil" if is_demo else "Resultados"
                    if len(top_n) <= 6:
                        item['chart_image'] = ChartGenerator.generate_bar_chart(
                            item['chart_labels'],
                            item['chart_data'],
                            title,
                            dark_mode=dark_mode,
                        )
                    else:
                        item['chart_image'] = (
                            ChartGenerator.generate_horizontal_bar_chart(
                                item['chart_labels'],
                                item['chart_data'],
                                title,
                                dark_mode=dark_mode,
                            )
                        )

            # --- Texto ---
            elif qid in text_responses:
                previous_insight_context = None
                raw_texts = text_responses[qid]
                clean_texts = SensitiveDataFilter.sanitize_text_responses(raw_texts)
                item['total_respuestas'] = len(clean_texts)
                item['samples_texto'] = clean_texts[:100]
                topics_html = TextMiningEngine.extract_topics(clean_texts)
                # Contexto adicional
                context_lines = [
                    f"<b>Total de comentarios:</b> {len(clean_texts)}",
                ]
                if len(clean_texts) > 0:
                    context_lines.append(f"<b>Ejemplo:</b> {clean_texts[0][:120]}{'...' if len(clean_texts[0]) > 120 else ''}")
                context_html = "<br>".join(context_lines)
                strategy = "💡 <strong>Recomendación:</strong> Profundizar en los temas clave detectados para identificar oportunidades de mejora o fortalezas."
                item['insight'] = f"""
                    <div class='p-3 bg-body-tertiary rounded'>
                        <p class='mb-1 text-body-emphasis'>
                            <strong>Temas clave detectados:</strong> {topics_html}
                        </p>
                        <div class='mb-2 small'>{context_html}</div>
                        <div class='mt-2 pt-2 border-top border-secondary-subtle text-body-secondary small'>{strategy}</div>
                    </div>
                """

            analysis_data.append(item)

        # 7) KPI global + meta-resumen ejecutivo
        kpi_score = (
            sum(satisfaction_scores) / len(satisfaction_scores)
            if satisfaction_scores
            else 0
        )

        meta = SurveyAnalysisService._build_meta(
            survey=survey,
            questions=questions,
            analyzable_q=analyzable_q,
            kpi_score=kpi_score,
            evolution_data=evolution_data,
            analysis_data=analysis_data,
            total_responses=total_responses,
        )

        result = {
            'analysis_data': analysis_data,
            'kpi_prom_satisfaccion': kpi_score,
            'evolution_chart': evolution_data,
            'ignored_questions': skipped_log,
            'meta': meta,
            'nps_data': nps_data,
            'heatmap_image': heatmap_image,
        }

        cache.set(cache_key, result, CACHE_TIMEOUT_ANALYSIS)
        
        # CORRECCIÓN: El return está correctamente indentado dentro de la función
        return result

    @staticmethod
    def _build_empty_response(skipped):
        """Respuesta coherente cuando no hay datos analizables."""
        meta = {
            'generated_at': timezone.now().isoformat(),
            'headline': "Sin datos suficientes para análisis",
            'subheadline': "La encuesta aún no cuenta con suficientes respuestas para generar indicadores.",
            'sample': {
                'total_responses': 0,
                'period_label': "Sin periodo definido",
            },
            'structure': {
                'total_questions': 0,
                'analyzable_questions': 0,
                'numeric_questions': 0,
                'categorical_questions': 0,
                'text_questions': 0,
                'demographic_questions': 0,
            },
            'highlights': [],
            'alerts': [],
        }
        return {
            'analysis_data': [],
            'ignored_questions': skipped,
            'evolution_chart': {
                'labels': [],
                'data': [],
                'source': 'NONE',
                'warning': None,
                'question_used': None,
            },
            'kpi_prom_satisfaccion': 0,
            'meta': meta,
            'nps_data': {
                'score': None,
                'promoters': 0,
                'passives': 0,
                'detractors': 0,
            },
            'heatmap_image': None,
        }

    @staticmethod
    def _init_item(q, order):
        return {
            'id': q.id,
            'text': q.text,
            'type': q.type,
            'order': order,
            'tipo_display': q.get_type_display(),
            'insight': '',
            'options': [],
            'chart_data': [],
        }

    @staticmethod
    def _build_meta(
        survey,
        questions,
        analyzable_q,
        kpi_score,
        evolution_data,
        analysis_data,
        total_responses,
    ):
        """Resumen ejecutivo pensado como tablero de consultoría."""
        num_q = sum(1 for q in analyzable_q if q.type in {'scale', 'number'})
        cat_q = sum(1 for q in analyzable_q if q.type in {'single', 'multi'})
        txt_q = sum(1 for q in analyzable_q if q.type == 'text')
        demo_q = sum(
            1
            for q in analyzable_q
            if getattr(q, 'analysis_category', 'VALID') == 'DEMO'
        )

        # Periodo analizado (según timeline ya limitado)
        if evolution_data and evolution_data.get('labels'):
            labels = evolution_data['labels']
            if len(labels) == 1:
                period_label = f"Datos del {labels[0]}"
            else:
                period_label = f"De {labels[0]} a {labels[-1]}"
        else:
            period_label = "Sin referencia temporal disponible"

        # Detectar fortalezas y riesgos a partir de preguntas numéricas
        strengths = []
        risks = []
        for item in analysis_data:
            if item.get('type') not in ('scale', 'number'):
                continue
            if item.get('total_respuestas', 0) < 20:
                continue

            avg = item.get('avg') or 0
            score_norm = item.get('score_norm', None)
            state = item.get('state', None)

            entry = {
                'id': item.get('id'),
                'text': item.get('text'),
                'avg': round(float(avg), 2),
                'score_norm': score_norm,
                'state': state,
            }

            # Estados positivos vs de riesgo (reutilizando tu semántica)
            if state in ('EXCELENTE', 'BUENO', 'success', 'primary'):
                strengths.append(entry)
            elif state in ('REGULAR', 'CRITICO', 'danger', 'warning'):
                risks.append(entry)

        def _score_key(x):
            if x.get('score_norm') is not None:
                return x['score_norm']
            return x['avg']

        strengths = sorted(strengths, key=_score_key, reverse=True)[:3]
        risks = sorted(risks, key=_score_key)[:3]

        # Mood global según KPI
        if kpi_score >= 8.5:
            mood = "Zona sobresaliente"
        elif kpi_score >= 7.0:
            mood = "Experiencia sólida"
        elif kpi_score >= 5.0:
            mood = "Zona intermedia / oportunidades de mejora"
        else:
            mood = "Zona crítica: urge priorizar acciones"

        headline = (
            f"Índice global de experiencia: {kpi_score:.1f}/10"
            if kpi_score
            else "Análisis global sin indicador de satisfacción"
        )

        return {
            'generated_at': timezone.now().isoformat(),
            'headline': headline,
            'subheadline': mood,
            'sample': {
                'survey_id': survey.id,
                'title': getattr(survey, 'title', str(survey)),
                'total_responses': total_responses,
                'period_label': period_label,
            },
            'structure': {
                'total_questions': len(questions),
                'analyzable_questions': len(analyzable_q),
                'numeric_questions': num_q,
                'categorical_questions': cat_q,
                'text_questions': txt_q,
                'demographic_questions': demo_q,
            },
            'highlights': strengths,
            'alerts': risks,
        }