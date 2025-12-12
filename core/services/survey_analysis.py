"""core/services/survey_analysis.py"""
import logging
import math
import re
import random
import unicodedata
import numpy as np
import pandas as pd
from collections import defaultdict, Counter
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from core.utils.logging_utils import log_performance
from surveys.models import Question, SurveyResponse, QuestionResponse

logger = logging.getLogger(__name__)
CACHE_TIMEOUT_ANALYSIS = 3600

# --- 1. UTILIDADES Y CONSTANTES ---

class NarrativeUtils:
    @staticmethod
    def get_template(key, templates_dict, seed_source):
        options = templates_dict.get(key, ["Sin análisis disponible."])
        rng = random.Random(seed_source)
        return rng.choice(options)

class AnalysisConstants:
    STOP_WORDS = {
        'este', 'esta', 'estas', 'estos', 'para', 'pero', 'porque', 'pues', 'solo', 'sobre', 'todo', 
        'que', 'con', 'los', 'las', 'una', 'uno', 'unos', 'unas', 'del', 'por', 'estoy', 'estan',
        'usted', 'ustedes', 'ellos', 'ellas', 'ser', 'son', 'era', 'eran', 'fue', 'fueron', 'muy', 'mas',
        'the', 'and', 'this', 'that', 'with', 'from', 'have', 'been', 'user_agent', 'browser', 'null', 'nan',
        'gracias', 'hola', 'adios', 'buenos', 'dias', 'tardes', 'noches', 'encuesta', 'respuesta', 'comentario',
        'bien', 'mal', 'regular', 'excelente', 'bueno', 'malo', 'satisfecho', 'servicio', 'si', 'no', 'mi', 'me'
    }

def normalize_text(text):
    if not text: return ''
    text_str = str(text)
    text_str = text_str.translate(str.maketrans('', '', '¿?¡!_-.[](){}:,"'))
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()

# --- 2. MOTORES DE NARRATIVA ---

class DemographicNarrative:
    RESULTADOS = {
        'UNANIMOUS': [
            "De {total} personas, casi todos eligieron **{top1}** ({pct1:.1f}%).",
            "Casi todos están de acuerdo: **{top1}** es la opción favorita ({pct1:.1f}%).",
            "La mayoría eligió **{top1}**. No hay dudas, es la opción clara ({pct1:.1f}%).",
            "Muchos piensan igual y prefieren **{top1}** ({pct1:.1f}%).",
            "Casi nadie eligió otra cosa que no sea **{top1}** ({pct1:.1f}%).",
            "Todos van por **{top1}**, casi nadie eligió otra cosa.",
            "Está clarísimo: **{top1}** es la opción de todos.",
            "No hay discusión, todos prefieren **{top1}**.",
            "El grupo piensa igual, todos eligen **{top1}**.",
            "**{top1}** arrasó, nadie eligió otra cosa.",
            "No hay variedad, todos fueron por **{top1}**.",
            "La respuesta es casi unánime: **{top1}**.",
            "No hay dudas, la opción es **{top1}**.",
            "Todos coinciden en **{top1}**.",
            "La mayoría absoluta eligió **{top1}**.",
            "No hay competencia, solo **{top1}**.",
            "Todos piensan igual, eligen **{top1}**.",
            "No hay otra opción, solo **{top1}**.",
            "El grupo está de acuerdo: **{top1}**.",
            "No hay variedad, solo **{top1}**.",
            "Todos eligieron lo mismo: **{top1}**.",
            "No hay dudas, todos van por **{top1}**.",
            "La opción clara es **{top1}**.",
            "No hay discusión, todos eligieron igual.",
            "Todos eligieron la misma opción: **{top1}**.",
            "No hay otra respuesta, solo **{top1}**.",
            "Todos están de acuerdo, es **{top1}**.",
            "No hay variedad, todos eligieron igual.",
            "La respuesta es clara: **{top1}**.",
            "Todos eligieron **{top1}**, nadie eligió otra cosa."
        ],
        'DOMINANT': [
            "La mayoría eligió **{top1}** ({pct1:.1f}%), aunque hay otras opciones.",
            "**{top1}** es la opción más elegida, pero no la única ({pct1:.1f}%).",
            "Se nota que a muchos les gusta **{top1}**, aunque hay variedad ({pct1:.1f}%).",
            "**{top1}** va ganando, pero hay otras respuestas también ({pct1:.1f}%).",
            "La gente prefiere **{top1}**, pero no todos piensan igual ({pct1:.1f}%).",
            "**{top1}** es la opción principal, pero hay otras en juego.",
            "La mayoría va por **{top1}**, pero no todos.",
            "**{top1}** lidera, pero hay otras opciones.",
            "Muchos eligieron **{top1}**, pero no todos.",
            "**{top1}** es la más elegida, pero hay variedad.",
            "La mayoría se inclinó por **{top1}**.",
            "**{top1}** es la favorita, pero no la única.",
            "Hay una clara preferencia por **{top1}**.",
            "**{top1}** es la más votada, pero hay otras.",
            "La mayoría eligió **{top1}**, pero hay otras opciones.",
            "**{top1}** es la más popular, pero no la única.",
            "Muchos eligieron **{top1}**, pero hay variedad.",
            "**{top1}** es la opción principal, pero no la única.",
            "La mayoría va por **{top1}**, pero hay otras opciones.",
            "**{top1}** lidera, pero no todos la eligieron.",
            "Muchos eligieron **{top1}**, pero hay otras respuestas.",
            "**{top1}** es la más elegida, pero no la única.",
            "La mayoría se inclinó por **{top1}**, pero hay variedad.",
            "**{top1}** es la favorita, pero hay otras opciones.",
            "Hay una clara preferencia por **{top1}**, pero no es la única.",
            "**{top1}** es la más votada, pero hay otras respuestas.",
            "La mayoría eligió **{top1}**, pero hay otras respuestas.",
            "**{top1}** es la más popular, pero hay otras opciones.",
            "Muchos eligieron **{top1}**, pero no todos la eligieron."
        ],
        'DUAL': [
            "Las respuestas están divididas entre **{top1}** ({pct1:.1f}%) y **{top2}** ({pct2:.1f}%).",
            "Hay dos opciones que destacan: **{top1}** y **{top2}**.",
            "El grupo se reparte entre **{top1}** y **{top2}**.",
            "No hay un solo favorito, sino dos: **{top1}** y **{top2}**.",
            "Las opiniones están bastante parejas entre **{top1}** y **{top2}**.",
            "El grupo está dividido entre **{top1}** y **{top2}**.",
            "No hay un claro ganador, están entre **{top1}** y **{top2}**.",
            "Las respuestas se reparten entre **{top1}** y **{top2}**.",
            "Hay empate entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia entre **{top1}** y **{top2}**.",
            "El grupo está casi empatado entre **{top1}** y **{top2}**.",
            "Las dos opciones más elegidas son **{top1}** y **{top2}**.",
            "No hay un favorito claro, están entre **{top1}** y **{top2}**.",
            "El grupo se divide entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia, están entre **{top1}** y **{top2}**.",
            "Las respuestas están muy parejas entre **{top1}** y **{top2}**.",
            "No hay un claro ganador, están entre **{top1}** y **{top2}**.",
            "Las respuestas se reparten entre **{top1}** y **{top2}**.",
            "Hay empate entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia entre **{top1}** y **{top2}**.",
            "El grupo está casi empatado entre **{top1}** y **{top2}**.",
            "Las dos opciones más elegidas son **{top1}** y **{top2}**.",
            "No hay un favorito claro, están entre **{top1}** y **{top2}**.",
            "El grupo se divide entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia, están entre **{top1}** y **{top2}**.",
            "Las respuestas están muy parejas entre **{top1}** y **{top2}**.",
            "No hay un claro ganador, están entre **{top1}** y **{top2}**.",
            "Las respuestas se reparten entre **{top1}** y **{top2}**.",
            "Hay empate entre **{top1}** y **{top2}**."
        ],
        'COMPETITIVE': [
            "Las respuestas están muy repartidas, no hay un claro favorito.",
            "Nadie se pone de acuerdo, hay muchas opciones distintas.",
            "No hay una opción que gane por mucho, todos eligieron cosas diferentes.",
            "Las opiniones son muy variadas, no hay un líder claro.",
            "Cada quien eligió algo distinto, no hay una tendencia fuerte.",
            "No hay una opción que destaque, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder."
        ]
    }

    INTERPRETACIONES = {
        'UNANIMOUS': [
            "El grupo está muy alineado en su elección.",
            "No hay dudas sobre la preferencia del grupo.",
            "Todos piensan igual en este tema.",
            "La decisión es clara para todos."
        ],
        'DOMINANT': [
            "Hay una preferencia clara, pero también diversidad.",
            "La mayoría coincide, aunque hay otras opiniones.",
            "Predomina una opción, pero no es la única.",
            "Se nota una tendencia, pero no es absoluta."
        ],
        'DUAL': [
            "El grupo está dividido entre dos opciones principales.",
            "No hay un solo favorito, hay dos que compiten.",
            "Las opiniones están bastante parejas.",
            "No hay mucha diferencia entre las dos más elegidas."
        ],
        'COMPETITIVE': [
            "No hay una opción clara, todos eligieron diferente.",
            "El grupo está muy repartido, no hay un líder.",
            "Las opiniones son muy variadas.",
            "No hay una tendencia fuerte, todos piensan distinto."
        ]
    }

    RECOMENDACIONES = {
        'UNANIMOUS': [
            "¡Buen trabajo! Sigan así.",
            "No cambien nada, funciona bien.",
            "Mantener lo que están haciendo, va perfecto.",
            "Seguir igual, todos están conformes."
        ],
        'DOMINANT': [
            "Quizás valga la pena preguntar por qué algunos eligen otras opciones.",
            "Escuchar a los que piensan distinto puede ayudar.",
            "Ver si se puede mejorar para los que no eligieron la opción principal.",
            "Buscar qué hace que algunos elijan otra cosa."
        ],
        'DUAL': [
            "Sería bueno saber qué hace que la gente se divida entre estas dos opciones.",
            "Preguntar más para entender por qué hay dos opciones fuertes.",
            "Ver si hay algo en común entre los que eligen cada opción.",
            "Buscar qué diferencia a los dos grupos."
        ],
        'COMPETITIVE': [
            "Hay mucha variedad, tal vez conviene preguntar más para entender mejor.",
            "Escuchar a todos puede ayudar a encontrar un camino.",
            "Buscar si hay algo que una al grupo.",
            "Ver si se puede simplificar para que haya más acuerdo."
        ]
    }

    @staticmethod
    def analyze(dist, total, question, seed, n_sentences=3):
        if not dist or total == 0:
            return "Datos insuficientes para generar insights."

        sorted_dist = sorted(dist, key=lambda x: x['count'], reverse=True)
        top1 = sorted_dist[0]
        top1_pct = (top1['count'] / total) * 100
        top2 = sorted_dist[1] if len(sorted_dist) > 1 else None
        top2_pct = (top2['count'] / total) * 100 if top2 else 0
        sum_top2 = top1_pct + top2_pct

        key = 'COMPETITIVE'
        if top1_pct >= 80:
            key = 'UNANIMOUS'
        elif top1_pct >= 55:
            key = 'DOMINANT'
        elif top2 and (top1_pct - top2_pct) < 15 and sum_top2 > 60:
            key = 'DUAL'

        rng = random.Random(seed)
        # Selecciona frases no repetidas y coherentes
        n = min(n_sentences, len(DemographicNarrative.RESULTADOS[key]), len(DemographicNarrative.INTERPRETACIONES[key]), len(DemographicNarrative.RECOMENDACIONES[key]))
        resultados = rng.sample(DemographicNarrative.RESULTADOS[key], n)
        interpretaciones = rng.sample(DemographicNarrative.INTERPRETACIONES[key], n)
        recomendaciones = rng.sample(DemographicNarrative.RECOMENDACIONES[key], n)
        frases = []
        for i in range(n):
            r = resultados[i].format(
                top1=top1['option'], pct1=top1_pct,
                top2=top2['option'] if top2 else 'otra', pct2=top2_pct,
                sum_pct=sum_top2, total=total
            )
            it = interpretaciones[i]
            rec = recomendaciones[i]
            frases.append(f"{r} {it} {rec}")
        return " ".join(frases)
    GENERIC_TEMPLATES = {
        'UNANIMOUS': [
            "De {total} personas, casi todos eligieron **{top1}** ({pct1:.1f}%).",
            "Casi todos están de acuerdo: **{top1}** es la opción favorita ({pct1:.1f}%).",
            "La mayoría eligió **{top1}**. No hay dudas, es la opción clara ({pct1:.1f}%).",
            "Muchos piensan igual y prefieren **{top1}** ({pct1:.1f}%).",
            "Casi nadie eligió otra cosa que no sea **{top1}** ({pct1:.1f}%).",
            "Todos van por **{top1}**, casi nadie eligió otra cosa.",
            "Está clarísimo: **{top1}** es la opción de todos.",
            "No hay discusión, todos prefieren **{top1}**.",
            "El grupo piensa igual, todos eligen **{top1}**.",
            "**{top1}** arrasó, nadie eligió otra cosa.",
            "No hay variedad, todos fueron por **{top1}**.",
            "La respuesta es casi unánime: **{top1}**.",
            "No hay dudas, la opción es **{top1}**.",
            "Todos coinciden en **{top1}**.",
            "La mayoría absoluta eligió **{top1}**.",
            "No hay competencia, solo **{top1}**.",
            "Todos piensan igual, eligen **{top1}**.",
            "No hay otra opción, solo **{top1}**.",
            "El grupo está de acuerdo: **{top1}**.",
            "No hay variedad, solo **{top1}**.",
            "Todos eligieron lo mismo: **{top1}**.",
            "No hay dudas, todos van por **{top1}**.",
            "La opción clara es **{top1}**.",
            "No hay discusión, todos eligieron igual.",
            "Todos eligieron la misma opción: **{top1}**.",
            "No hay otra respuesta, solo **{top1}**.",
            "Todos están de acuerdo, es **{top1}**.",
            "No hay variedad, todos eligieron igual.",
            "La respuesta es clara: **{top1}**.",
            "Todos eligieron **{top1}**, nadie eligió otra cosa."
        ],
        'DOMINANT': [
            "La mayoría eligió **{top1}** ({pct1:.1f}%), aunque hay otras opciones.",
            "**{top1}** es la opción más elegida, pero no la única ({pct1:.1f}%).",
            "Se nota que a muchos les gusta **{top1}**, aunque hay variedad ({pct1:.1f}%).",
            "**{top1}** va ganando, pero hay otras respuestas también ({pct1:.1f}%).",
            "La gente prefiere **{top1}**, pero no todos piensan igual ({pct1:.1f}%).",
            "**{top1}** es la opción principal, pero hay otras en juego.",
            "La mayoría va por **{top1}**, pero no todos.",
            "**{top1}** lidera, pero hay otras opciones.",
            "Muchos eligieron **{top1}**, pero no todos.",
            "**{top1}** es la más elegida, pero hay variedad.",
            "La mayoría se inclinó por **{top1}**.",
            "**{top1}** es la favorita, pero no la única.",
            "Hay una clara preferencia por **{top1}**.",
            "**{top1}** es la más votada, pero hay otras.",
            "La mayoría eligió **{top1}**, pero hay otras opciones.",
            "**{top1}** es la más popular, pero no la única.",
            "Muchos eligieron **{top1}**, pero hay variedad.",
            "**{top1}** es la opción principal, pero no la única.",
            "La mayoría va por **{top1}**, pero hay otras opciones.",
            "**{top1}** lidera, pero no todos la eligieron.",
            "Muchos eligieron **{top1}**, pero hay otras respuestas.",
            "**{top1}** es la más elegida, pero no la única.",
            "La mayoría se inclinó por **{top1}**, pero hay variedad.",
            "**{top1}** es la favorita, pero hay otras opciones.",
            "Hay una clara preferencia por **{top1}**, pero no es la única.",
            "**{top1}** es la más votada, pero hay otras respuestas.",
            "La mayoría eligió **{top1}**, pero hay otras respuestas.",
            "**{top1}** es la más popular, pero hay otras opciones.",
            "Muchos eligieron **{top1}**, pero no todos la eligieron."
        ],
        'DUAL': [
            "Las respuestas están divididas entre **{top1}** ({pct1:.1f}%) y **{top2}** ({pct2:.1f}%).",
            "Hay dos opciones que destacan: **{top1}** y **{top2}**.",
            "El grupo se reparte entre **{top1}** y **{top2}**.",
            "No hay un solo favorito, sino dos: **{top1}** y **{top2}**.",
            "Las opiniones están bastante parejas entre **{top1}** y **{top2}**.",
            "El grupo está dividido entre **{top1}** y **{top2}**.",
            "No hay un claro ganador, están entre **{top1}** y **{top2}**.",
            "Las respuestas se reparten entre **{top1}** y **{top2}**.",
            "Hay empate entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia entre **{top1}** y **{top2}**.",
            "El grupo está casi empatado entre **{top1}** y **{top2}**.",
            "Las dos opciones más elegidas son **{top1}** y **{top2}**.",
            "No hay un favorito claro, están entre **{top1}** y **{top2}**.",
            "El grupo se divide entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia, están entre **{top1}** y **{top2}**.",
            "Las respuestas están muy parejas entre **{top1}** y **{top2}**.",
            "No hay un claro ganador, están entre **{top1}** y **{top2}**.",
            "Las respuestas se reparten entre **{top1}** y **{top2}**.",
            "Hay empate entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia entre **{top1}** y **{top2}**.",
            "El grupo está casi empatado entre **{top1}** y **{top2}**.",
            "Las dos opciones más elegidas son **{top1}** y **{top2}**.",
            "No hay un favorito claro, están entre **{top1}** y **{top2}**.",
            "El grupo se divide entre **{top1}** y **{top2}**.",
            "No hay mucha diferencia, están entre **{top1}** y **{top2}**.",
            "Las respuestas están muy parejas entre **{top1}** y **{top2}**.",
            "No hay un claro ganador, están entre **{top1}** y **{top2}**.",
            "Las respuestas se reparten entre **{top1}** y **{top2}**.",
            "Hay empate entre **{top1}** y **{top2}**."
        ],
        'COMPETITIVE': [
            "Las respuestas están muy repartidas, no hay un claro favorito.",
            "Nadie se pone de acuerdo, hay muchas opciones distintas.",
            "No hay una opción que gane por mucho, todos eligieron cosas diferentes.",
            "Las opiniones son muy variadas, no hay un líder claro.",
            "Cada quien eligió algo distinto, no hay una tendencia fuerte.",
            "No hay una opción que destaque, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder.",
            "No hay una opción que sobresalga, todos eligieron diferente.",
            "Las respuestas son muy variadas, no hay un favorito.",
            "No hay un claro ganador, todos eligieron diferente.",
            "Las opiniones están muy repartidas, no hay un líder."
        ]
    }

class NumericNarrative:
    RESULTADOS = {
        'EXCELENTE': [
            "El promedio fue altísimo: {avg:.1f} de {max_val}.",
            "Casi todos pusieron puntajes altos, promedio de {avg:.1f}.",
            "El resultado es excelente, promedio de {avg:.1f}.",
            "El puntaje promedio es muy alto: {avg:.1f}.",
            "El grupo está muy conforme, promedio de {avg:.1f}.",
            "El grupo está muy satisfecho, promedio de {avg:.1f}."
        ],
        'ALTO': [
            "El promedio fue bueno: {avg:.1f}.",
            "La mayoría puso puntajes altos, promedio de {avg:.1f}.",
            "El resultado es bueno, promedio de {avg:.1f}.",
            "El puntaje promedio es alto: {avg:.1f}.",
            "El grupo está conforme, promedio de {avg:.1f}.",
            "El grupo está satisfecho, promedio de {avg:.1f}."
        ],
        'MEDIO': [
            "El promedio fue regular: {avg:.1f}.",
            "La mayoría puso puntajes medios, promedio de {avg:.1f}.",
            "El resultado es aceptable, promedio de {avg:.1f}.",
            "El puntaje promedio es medio: {avg:.1f}.",
            "El grupo está más o menos conforme, promedio de {avg:.1f}.",
            "El grupo está medianamente satisfecho, promedio de {avg:.1f}."
        ],
        'BAJO': [
            "El promedio fue bajo: {avg:.1f}.",
            "La mayoría puso puntajes bajos, promedio de {avg:.1f}.",
            "No fue un buen resultado, promedio de {avg:.1f}.",
            "El puntaje promedio es bajo: {avg:.1f}.",
            "El grupo no está conforme, promedio de {avg:.1f}.",
            "El grupo no está satisfecho, promedio de {avg:.1f}."
        ],
        'CRITICO': [
            "El promedio es muy bajo: {avg:.1f}.",
            "Casi todos pusieron puntajes bajos, promedio de {avg:.1f}.",
            "El resultado es preocupante, solo {avg:.1f} de {max_val}.",
            "El puntaje es muy bajo: {avg:.1f}.",
            "El grupo está muy disconforme, promedio de {avg:.1f}.",
            "El grupo está muy insatisfecho, promedio de {avg:.1f}."
        ],
        'SIN_MAX': [
            "El promedio fue de {avg:.1f}.",
            "No hay un máximo, pero el promedio es {avg:.1f}.",
            "El valor medio es {avg:.1f}.",
            "Promedio: {avg:.1f}.",
            "El grupo sacó un promedio de {avg:.1f}."
        ]
    }
    INTERPRETACIONES = {
        'EXCELENTE': [
            "La gente está muy contenta con el resultado.",
            "Se nota que la mayoría está satisfecha.",
            "El grupo está muy conforme con lo que recibió.",
            "El resultado muestra mucha satisfacción."
        ],
        'ALTO': [
            "La mayoría está conforme, pero siempre se puede mejorar.",
            "El grupo está bastante satisfecho.",
            "El resultado es bueno, pero hay margen para subirlo más.",
            "La gente está contenta, pero se puede apuntar más alto."
        ],
        'MEDIO': [
            "No está mal, pero hay cosas para mejorar.",
            "El grupo está más o menos conforme.",
            "El resultado es regular, se puede mejorar.",
            "Hay opiniones divididas, algunos conformes y otros no tanto."
        ],
        'BAJO': [
            "A muchos no les gustó, hay que mejorar.",
            "El grupo no está conforme, hay que hacer cambios.",
            "El resultado no fue bueno, hay que trabajar en eso.",
            "La mayoría no está satisfecha."
        ],
        'CRITICO': [
            "El grupo está muy disconforme, hay que cambiar urgente.",
            "El resultado es muy malo, hay que actuar ya.",
            "Casi nadie está conforme, es preocupante.",
            "El grupo está muy insatisfecho, hay que mejorar mucho."
        ],
        'SIN_MAX': [
            "No hay referencia máxima, pero se puede mejorar.",
            "No hay máximo, pero el grupo puede estar más conforme.",
            "Sin máximo, pero siempre se puede mejorar.",
            "No hay máximo, pero el resultado es mejorable."
        ]
    }
    RECOMENDACIONES = {
        'EXCELENTE': [
            "¡Sigan así!",
            "No cambien nada, van muy bien.",
            "Mantener lo que están haciendo, funciona perfecto.",
            "Compartir lo que hacen con otros grupos."
        ],
        'ALTO': [
            "Van bien, pero pueden mejorar un poco más.",
            "Seguir así y buscar pequeños cambios para mejorar.",
            "Ajustar detalles para llegar al máximo.",
            "No bajar los brazos, pueden llegar más alto."
        ],
        'MEDIO': [
            "Hay que trabajar para mejorar el promedio.",
            "Buscar qué se puede cambiar para subir el resultado.",
            "Escuchar a los que no están conformes.",
            "Probar nuevas ideas para mejorar."
        ],
        'BAJO': [
            "Hay que hacer cambios para mejorar.",
            "Revisar qué no está funcionando.",
            "Hablar con el grupo para ver qué mejorar.",
            "Buscar soluciones para subir el promedio."
        ],
        'CRITICO': [
            "Cambiar urgente lo que no funciona.",
            "Actuar rápido para mejorar el resultado.",
            "Escuchar a todos y hacer cambios grandes.",
            "No esperar más, hay que mejorar ya."
        ],
        'SIN_MAX': [
            "Juntar más datos ayuda a entender mejor.",
            "Buscar más información para comparar.",
            "Seguir midiendo para ver si mejora.",
            "No bajar los brazos, siempre se puede mejorar."
        ]
    }

    @staticmethod
    def analyze(avg, max_val, n_sentences=3):
        import random
        if not max_val or max_val == 0:
            key = 'SIN_MAX'
            rng = random.Random(str(avg))
        else:
            pct = (avg / max_val) * 100
            if pct >= 90:
                key = 'EXCELENTE'
            elif pct >= 75:
                key = 'ALTO'
            elif pct >= 60:
                key = 'MEDIO'
            elif pct >= 40:
                key = 'BAJO'
            else:
                key = 'CRITICO'
            rng = random.Random(str(avg) + str(max_val))

        n = min(n_sentences, len(NumericNarrative.RESULTADOS[key]), len(NumericNarrative.INTERPRETACIONES[key]), len(NumericNarrative.RECOMENDACIONES[key]))
        resultados = rng.sample(NumericNarrative.RESULTADOS[key], n)
        interpretaciones = rng.sample(NumericNarrative.INTERPRETACIONES[key], n)
        recomendaciones = rng.sample(NumericNarrative.RECOMENDACIONES[key], n)
        frases = []
        for i in range(n):
            r = resultados[i].format(avg=avg, max_val=max_val)
            it = interpretaciones[i]
            rec = recomendaciones[i]
            frases.append(f"{r} {it} {rec}")
        return " ".join(frases)

    @staticmethod
    def analyze_multiple(avg, max_val, n_sentences=3):
        # Si se quiere devolver varias frases no repetidas
        import random
        if not max_val or max_val == 0:
            key = 'SIN_MAX'
            rng = random.Random(str(avg))
        else:
            pct = (avg / max_val) * 100
            if pct >= 90:
                key = 'EXCELENTE'
            elif pct >= 75:
                key = 'ALTO'
            elif pct >= 60:
                key = 'MEDIO'
            elif pct >= 40:
                key = 'BAJO'
            else:
                key = 'CRITICO'
            rng = random.Random(str(avg) + str(max_val))
        resultados = rng.sample(NumericNarrative.RESULTADOS[key], min(n_sentences, len(NumericNarrative.RESULTADOS[key])))
        interpretaciones = rng.sample(NumericNarrative.INTERPRETACIONES[key], min(n_sentences, len(NumericNarrative.INTERPRETACIONES[key])))
        recomendaciones = rng.sample(NumericNarrative.RECOMENDACIONES[key], min(n_sentences, len(NumericNarrative.RECOMENDACIONES[key])))
        frases = []
        for i in range(n_sentences):
            r = resultados[i % len(resultados)].format(avg=avg, max_val=max_val)
            it = interpretaciones[i % len(interpretaciones)]
            rec = recomendaciones[i % len(recomendaciones)]
            frases.append(f"{r} {it} {rec}")
        return " ".join(frases)

    # ---
    # Fin NumericNarrative

    @staticmethod
    def analyze(dist, total, question, seed, n_sentences=3):
        # Versión corregida: solo la lógica de DemographicNarrative, sin duplicados ni mezcla con NumericNarrative
        if not dist or total == 0:
            return "Datos insuficientes para generar insights."

        sorted_dist = sorted(dist, key=lambda x: x['count'], reverse=True)
        top1 = sorted_dist[0]
        top1_pct = (top1['count'] / total) * 100
        top2 = sorted_dist[1] if len(sorted_dist) > 1 else None
        top2_pct = (top2['count'] / total) * 100 if top2 else 0
        sum_top2 = top1_pct + top2_pct

        key = 'COMPETITIVE'
        if top1_pct >= 80:
            key = 'UNANIMOUS'
        elif top1_pct >= 55:
            key = 'DOMINANT'
        elif top2 and (top1_pct - top2_pct) < 15 and sum_top2 > 60:
            key = 'DUAL'

        rng = random.Random(seed)
        resultado = rng.choice(DemographicNarrative.RESULTADOS[key]).format(
            top1=top1['option'], pct1=top1_pct,
            top2=top2['option'] if top2 else 'otra', pct2=top2_pct,
            sum_pct=sum_top2, total=total
        )
        interpretacion = rng.choice(DemographicNarrative.INTERPRETACIONES[key])
        recomendacion = rng.choice(DemographicNarrative.RECOMENDACIONES[key])
        return f"{resultado} {interpretacion} {recomendacion}"

    @staticmethod
    def analyze(avg, max_val, n_sentences=3):
        import random
        if not max_val or max_val == 0:
            key = 'SIN_MAX'
            rng = random.Random(str(avg))
        else:
            pct = (avg / max_val) * 100
            if pct >= 90:
                key = 'EXCELENTE'
            elif pct >= 75:
                key = 'ALTO'
            elif pct >= 60:
                key = 'MEDIO'
            elif pct >= 40:
                key = 'BAJO'
            else:
                key = 'CRITICO'
            rng = random.Random(str(avg) + str(max_val))

        resultado = rng.choice(NumericNarrative.RESULTADOS[key]).format(avg=avg, max_val=max_val)
        interpretacion = rng.choice(NumericNarrative.INTERPRETACIONES[key])
        recomendacion = rng.choice(NumericNarrative.RECOMENDACIONES[key])
        return f"{resultado} {interpretacion} {recomendacion}"

class TextMiningEngine:
    POSITIVE_WORDS = {'bien', 'bueno', 'excelente', 'genial', 'mejor', 'feliz', 'satisfecho', 'gracias', 'encanta', 'perfecto'}
    NEGATIVE_WORDS = {'mal', 'malo', 'pésimo', 'peor', 'horrible', 'lento', 'difícil', 'error', 'problema', 'queja', 'sucio'}

    @staticmethod
    def extract_topics_and_sentiment(texts):
        words = []
        pos_count = 0; neg_count = 0
        for text in texts:
            clean = normalize_text(text)
            tokens = [w for w in clean.split() if w not in AnalysisConstants.STOP_WORDS and len(w) > 3]
            words.extend(tokens)
            for w in tokens:
                if w in TextMiningEngine.POSITIVE_WORDS: pos_count += 1
                elif w in TextMiningEngine.NEGATIVE_WORDS: neg_count += 1
        
        total_sent = pos_count + neg_count
        sentiment_label = "Neutral"
        if total_sent > 0:
            score = (pos_count - neg_count) / total_sent
            if score > 0.2: sentiment_label = "Positivo"
            elif score < -0.2: sentiment_label = "Negativo"
            elif score != 0: sentiment_label = "Mixto"

        if not words: return [], sentiment_label
        topics = [item[0] for item in Counter(words).most_common(6)]
        return topics, sentiment_label

class TimelineEngine:
    @staticmethod
    def analyze_evolution(qs):
        from django.db.models.functions import TruncDate
        from django.db.models import Count
        data = qs.annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).order_by('date')
        labels = []; counts = []
        for entry in data:
            if entry['date']:
                labels.append(entry['date'].strftime('%d/%m'))
                counts.append(entry['count'])
        return {'labels': labels, 'data': counts}

# --- 3. MOTOR ESTADÍSTICO AVANZADO ---

class AdvancedStatisticsEngine:
    @staticmethod
    def load_dataframe(survey, responses_queryset):
        relevant_q_ids = list(survey.questions.filter(type__in=['scale', 'number', 'radio', 'select', 'checkbox']).values_list('id', flat=True))
        if not relevant_q_ids: return pd.DataFrame(), pd.DataFrame() 

        data = list(QuestionResponse.objects.filter(survey_response__in=responses_queryset, question_id__in=relevant_q_ids).values('survey_response_id', 'question_id', 'text_value', 'numeric_value', 'selected_option__text'))
        if not data: return pd.DataFrame(), pd.DataFrame()

        df_raw = pd.DataFrame(data)
        df_raw.rename(columns={'survey_response_id': 'id'}, inplace=True)
        df_raw['num_val'] = df_raw['numeric_value'].fillna(pd.to_numeric(df_raw['text_value'], errors='coerce'))
        df_raw['label_val'] = df_raw['selected_option__text'].fillna(df_raw['text_value'])

        df_num = df_raw.pivot(index='id', columns='question_id', values='num_val')
        df_num.columns = [f'q_{col}' for col in df_num.columns] 
        df_cat = df_raw.pivot(index='id', columns='question_id', values='label_val')
        return df_num, df_cat

    @staticmethod
    def calculate_cronbach_alpha(df):
        if df.empty or df.shape[1] < 2: return None
        df_clean = df.dropna()
        if df_clean.shape[0] < 5: return None
        item_variances = df_clean.var(axis=0, ddof=1)
        total_variance = df_clean.sum(axis=1).var(ddof=1)
        if total_variance == 0: return 0.0
        k = df.shape[1]
        try:
            alpha = (k / (k - 1)) * (1 - (item_variances.sum() / total_variance))
            return max(0, min(1, alpha))
        except ZeroDivisionError: return 0.0

    @staticmethod
    def get_correlation_matrix(df):
        if df.empty or df.shape[1] < 2: return None
        corr = df.corr(method='pearson').round(2)
        return corr.where(pd.notnull(corr), None).to_dict()

    @staticmethod
    def generate_crosstab(df_cat, survey, row_id, col_id):
        try:
            row_id = int(row_id); col_id = int(col_id)
            if row_id not in df_cat.columns or col_id not in df_cat.columns: return {"error": "Datos no disponibles."}
            row_data = df_cat[row_id].fillna("Sin Respuesta")
            col_data = df_cat[col_id].fillna("Sin Respuesta")
            q_map = {q.id: q.text for q in survey.questions.filter(id__in=[row_id, col_id])}
            crosstab = pd.crosstab(row_data, col_data, margins=True, margins_name="Total")
            return {
                "row_label": q_map.get(row_id, "Fila"),
                "col_label": q_map.get(col_id, "Columna"),
                "data": crosstab.to_dict(orient="split"),
                "html_table": crosstab.to_html(classes="table table-bordered table-sm")
            }
        except Exception as e:
            logger.error(f"Error crosstab: {e}")
            return {"error": str(e)}

    @staticmethod
    def calculate_nps(survey, responses_queryset):
        nps_q = survey.questions.filter(type__in=['scale', 'number'], text__icontains='recomendar').first()
        if not nps_q: return {'score': None, 'promoters':0, 'passives':0, 'detractors':0}
        with connection.cursor() as cursor:
            cursor.execute("SELECT numeric_value FROM surveys_questionresponse qr JOIN surveys_surveyresponse r ON qr.survey_response_id = r.id WHERE qr.question_id = %s AND r.survey_id = %s AND numeric_value IS NOT NULL", [nps_q.id, survey.id])
            rows = cursor.fetchall()
        values = [r[0] for r in rows]
        total = len(values)
        if total == 0: return {'score': None, 'promoters':0, 'passives':0, 'detractors':0}
        promoters = sum(1 for v in values if v >= 9)
        detractors = sum(1 for v in values if v <= 6)
        passives = total - (promoters + detractors)
        score = ((promoters - detractors) / total) * 100
        return {'score': round(score, 1), 'promoters': promoters, 'passives': passives, 'detractors': detractors, 'total': total}

# --- 4. SERVICIO PRINCIPAL INTEGRADO ---

class SurveyAnalysisService:
    
    # --- HELPER DE AGRUPACIÓN INTELIGENTE (TOP N + OTROS) ---
    @staticmethod
    def _prepare_chart_data(distribution, label_key, count_key, is_numeric=False, limit=9):
        """
        Prepara los datos para el gráfico aplicando lógica de 'Top N + Otros'.
        - is_numeric=True: Intenta mantener el orden natural (1,2,3) si hay pocos datos.
                           Si hay muchos (edad), agrupa por popularidad.
        """
        if not distribution:
            return {'labels': [], 'data': []}

        # CASO 1: Numérico Corto (Escalas 1-10) -> Orden Natural (1, 2, 3...)
        if is_numeric and len(distribution) <= 15:
            sorted_dist = sorted(distribution, key=lambda x: x[label_key]) # Ordenar por Valor
            return {
                'labels': [str(int(d[label_key])) for d in sorted_dist],
                'data': [d[count_key] for d in sorted_dist]
            }

        # CASO 2: Categórico o Numérico Largo (Edad, Depto) -> Orden por Popularidad (Top Votos)
        # Ordenamos por COUNT descendente
        sorted_by_votes = sorted(distribution, key=lambda x: x[count_key], reverse=True)
        
        # Si no supera el límite, devolvemos todo ordenado por votos
        if len(sorted_by_votes) <= limit:
            return {
                'labels': [str(d[label_key]) for d in sorted_by_votes],
                'data': [d[count_key] for d in sorted_by_votes]
            }

        # CASO 3: Agrupación "Otros" (La cola larga)
        top_n = sorted_by_votes[:limit]
        others = sorted_by_votes[limit:]
        
        other_count = sum(d[count_key] for d in others)
        
        labels = [str(d[label_key]) for d in top_n] + ["Otros"]
        data = [d[count_key] for d in top_n] + [other_count]
        
        return {'labels': labels, 'data': data}

    @staticmethod
    @log_performance(threshold_ms=2500)
    def get_analysis_data(survey, responses_queryset, include_charts=True, cache_key=None, use_base_filter=True):
        total = responses_queryset.count()
        if cache_key is None:
            last_id = responses_queryset.order_by('-id').values_list('id', flat=True).first() or 0
            cache_key = f"analysis_v3_full:{survey.id}:{total}:{last_id}"

        cached = cache.get(cache_key)
        if cached: return cached

        questions = list(survey.questions.prefetch_related('options').order_by('order'))
        analysis_data = []
        analyzable_q = [q for q in questions if q.type != 'section']

        if not analyzable_q or total == 0: return SurveyAnalysisService._build_empty_response()

        numeric_stats, numeric_dist = SurveyAnalysisService._fetch_numeric_stats(analyzable_q, responses_queryset)
        choice_dist = SurveyAnalysisService._fetch_choice_stats(analyzable_q, responses_queryset)
        text_responses = SurveyAnalysisService._fetch_text_responses(analyzable_q, responses_queryset)
        
        satisfaction_scores = []

        for idx, q in enumerate(analyzable_q, 1):
            item = {'id': q.id, 'text': q.text, 'type': q.type, 'order': idx, 'insight_data': {}}

            # --- Numérico (Escalas, Edad, NPS) ---
            if q.id in numeric_stats:
                st = numeric_stats[q.id]
                item.update(st)
                raw_dist = numeric_dist.get(q.id, [])

                # Usamos el Helper Inteligente para generar el gráfico
                item['chart'] = SurveyAnalysisService._prepare_chart_data(
                    raw_dist, label_key='value', count_key='count', is_numeric=True, limit=9
                )

                # Datos para la tarjeta
                avg_val = st['avg']
                narrative_num = NumericNarrative.analyze(avg_val, st['max'], n_sentences=3)
                item['insight_data'] = {
                    'type': 'numeric',
                    'average': avg_val, 'avg': avg_val,
                    'max': st['max'],
                    'key_insight': narrative_num
                }
                if avg_val is not None:
                    satisfaction_scores.append(avg_val)

            # --- Categórico (Selección Múltiple, Radios) ---
            elif q.id in choice_dist:
                raw_dist = choice_dist[q.id]

                # Usamos el Helper Inteligente (Siempre por popularidad)
                item['chart'] = SurveyAnalysisService._prepare_chart_data(
                    raw_dist, label_key='option', count_key='count', is_numeric=False, limit=9
                )

                # Para la narrativa usamos la distribución completa ordenada (sin agrupar 'Otros' para el texto)
                full_sorted = sorted(raw_dist, key=lambda x: x['count'], reverse=True)
                total_q = sum(d['count'] for d in full_sorted)
                narrative_cat = DemographicNarrative.analyze(full_sorted, total_q, q, q.id, n_sentences=3)

                item['insight_data'] = {
                    'type': 'categorical',
                    'narrative': narrative_cat,
                    'key_insight': narrative_cat,
                    'top_option': full_sorted[0] if full_sorted else None
                }

            # --- Texto Abierto ---
            elif q.id in text_responses:
                texts = text_responses[q.id]
                item['total_responses'] = len(texts)
                item['samples'] = texts[:5]
                topics, sentiment = TextMiningEngine.extract_topics_and_sentiment(texts)
                # Estructura narrativa más larga y adaptativa para texto abierto
                intro = f"Se leyeron {len(texts)} comentarios. "
                temas = f"La gente habló mucho de: {', '.join(topics[:5])}. " if topics else "No hubo temas que se repitan mucho. "
                sent = f"En general, el sentimiento es **{sentiment}**. "
                if sentiment == "Positivo":
                    interpret = "A la mayoría le gustó lo que recibió."
                elif sentiment == "Negativo":
                    interpret = "A varios no les gustó y hay cosas para mejorar."
                else:
                    interpret = "Hay opiniones de todo tipo, no hay una sola idea."
                recomend = "Leer los comentarios ayuda a ver qué se puede mejorar o mantener."
                insight_txt = intro + temas + sent + interpret + " " + recomend
                item['insight_data'] = {
                    'type': 'text', 'topics': topics,
                    'narrative': insight_txt, 'key_insight': insight_txt
                }
                item['top_responses'] = texts[:5]

            analysis_data.append(item)

        # ... (Resto sin cambios) ...
        advanced_stats = {}
        try:
            df_num, df_cat = AdvancedStatisticsEngine.load_dataframe(survey, responses_queryset)
            advanced_stats = {
                'cronbach_alpha': AdvancedStatisticsEngine.calculate_cronbach_alpha(df_num),
                'correlation_matrix': AdvancedStatisticsEngine.get_correlation_matrix(df_num)
            }
        except Exception: pass

        nps_data = AdvancedStatisticsEngine.calculate_nps(survey, responses_queryset)
        evolution = TimelineEngine.analyze_evolution(responses_queryset)
        kpi_score = (sum(satisfaction_scores)/len(satisfaction_scores)) if satisfaction_scores else 0

        result = {'analysis_data': analysis_data, 'kpi_score': round(kpi_score, 1), 'nps_data': nps_data, 'evolution': evolution, 'advanced_stats': advanced_stats}
        cache.set(cache_key, result, CACHE_TIMEOUT_ANALYSIS)
        return result

    @staticmethod
    def generate_crosstab(survey, row_id, col_id, queryset=None):
        from surveys.models import SurveyResponse
        qs = queryset or SurveyResponse.objects.filter(survey=survey)
        try:
            _, df_cat = AdvancedStatisticsEngine.load_dataframe(survey, qs)
            if df_cat.empty: return {"error": "Sin datos."}
            return AdvancedStatisticsEngine.generate_crosstab(df_cat, survey, row_id, col_id)
        except Exception as e: return {"error": str(e)}

    @staticmethod
    def _build_empty_response():
        return {'analysis_data': [], 'kpi_score': 0, 'nps_data': {}, 'evolution': {}, 'advanced_stats': {}}

    @staticmethod
    def _fetch_numeric_stats(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type in ['scale', 'number']]
        if not ids: return {}, {}
        query = qs.values('id').query
        sql, params = query.get_compiler(using=qs.db).as_sql()
        placeholders = ','.join(['%s'] * len(ids))
        stats = {}; dist = defaultdict(list)
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT question_id, COUNT(*), AVG(numeric_value), MAX(numeric_value) FROM surveys_questionresponse WHERE question_id IN ({placeholders}) AND numeric_value IS NOT NULL AND survey_response_id IN ({sql}) GROUP BY question_id", ids + list(params))
            for r in cursor.fetchall(): 
                stats[r[0]] = {'count': r[1], 'avg': float(r[2]) if r[2] else 0.0, 'max': r[3]}
            cursor.execute(f"SELECT question_id, numeric_value, COUNT(*) FROM surveys_questionresponse WHERE question_id IN ({placeholders}) AND numeric_value IS NOT NULL AND survey_response_id IN ({sql}) GROUP BY question_id, numeric_value", ids + list(params))
            for r in cursor.fetchall(): dist[r[0]].append({'value': r[1], 'count': r[2]})
        return stats, dist

    @staticmethod
    def _fetch_choice_stats(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type in ['single', 'multi', 'radio', 'select']]
        if not ids: return {}
        dist = defaultdict(list)
        query = qs.values('id').query
        sql, params = query.get_compiler(using=qs.db).as_sql()
        placeholders = ','.join(['%s'] * len(ids))
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT qr.question_id, ao.text, COUNT(*) FROM surveys_questionresponse qr JOIN surveys_answeroption ao ON qr.selected_option_id = ao.id WHERE qr.question_id IN ({placeholders}) AND qr.survey_response_id IN ({sql}) GROUP BY qr.question_id, ao.text", ids + list(params))
            for r in cursor.fetchall(): dist[r[0]].append({'option': r[1], 'count': r[2]})
        return dist

    @staticmethod
    def _fetch_text_responses(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type == 'text']
        if not ids: return {}
        res = defaultdict(list)
        query = qs.values('id').query
        sql, params = query.get_compiler(using=qs.db).as_sql()
        placeholders = ','.join(['%s'] * len(ids))
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT question_id, text_value FROM surveys_questionresponse WHERE question_id IN ({placeholders}) AND text_value <> '' AND survey_response_id IN ({sql})", ids + list(params))
            seen = defaultdict(int)
            for r in cursor.fetchall():
                if seen[r[0]] < 100: res[r[0]].append(r[1]); seen[r[0]] += 1
        return res