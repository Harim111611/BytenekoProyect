# coding: utf-8
"""
Utilidad para probar la generación de narrativas sin dependencias de Django.
Incluye solo las clases y funciones necesarias para analizar datos numéricos, categóricos y de texto.
"""
import random
import unicodedata
import re
from collections import Counter

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

class TextMiningEngine:
    POSITIVE_WORDS = {'bien', 'bueno', 'excelente', 'genial', 'mejor', 'feliz', 'satisfecho', 'gracias', 'encanta', 'perfecto'}
    NEGATIVE_WORDS = {'mal', 'malo', 'pésimo', 'peor', 'horrible', 'lento', 'difícil', 'error', 'problema', 'queja', 'sucio'}
    @staticmethod
    def extract_topics_and_sentiment(texts):
        words = []
        pos_count = 0; neg_count = 0
        for text in texts:
            clean = normalize_text(text)
            tokens = [w for w in clean.split() if len(w) > 3]
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

def normalize_text(text):
    if not text: return ''
    text_str = str(text)
    text_str = text_str.translate(str.maketrans('', '', '¿?¡!_-.[](){}:,"'))
    normalized = unicodedata.normalize('NFKD', text_str).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', normalized).strip().lower()
