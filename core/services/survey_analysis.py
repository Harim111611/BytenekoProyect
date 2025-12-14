"""core/services/survey_analysis.py"""
import random
import unicodedata
import re
from collections import defaultdict, Counter
from django.core.cache import cache
from django.db.models import Avg, Max, Min, Count
from django.db.models.functions import TruncDate
from surveys.models import QuestionResponse

# --- 1. MOTOR DE ENSAMBLAJE DE NARRATIVA ---

class NarrativeBuilder:
    """Construye párrafos fluidos conectando ideas de forma natural."""
    CONNECTORS = {
        'FORMAL': {
            'ADDITION': [
                'Asimismo,', 'Adicionalmente,', 'Por otro lado,', 'De igual manera,', 
                'Complementando lo anterior,', 'En este mismo sentido,', 'A su vez,',
                'Sumado a esto,', 'Paralelamente,', 'Cabe agregar que,', 'Además,',
                'En concordancia,', 'Siguiendo esta línea,', 'Como punto adicional,'
            ],
            'CONTRAST': [
                'No obstante,', 'Sin embargo,', 'Aunque', 'A pesar de esto,', 
                'Por el contrario,', 'Si bien', 'Contrastando con esto,', 
                'Pese a ello,', 'Aun así,', 'Aunque cabe matizar que,', 'Empero,',
                'A diferencia de lo esperado,', 'Contrariamente,'
            ],
            'CONCLUSION': [
                'En conclusión,', 'Por tanto,', 'Esto sugiere que', 'En consecuencia,', 
                'Como resultado,', 'Dicho esto, se recomienda', 'Para finalizar,', 
                'En resumen,', 'De esta forma,', 'Así pues,', 'Finalmente,',
                'Por consiguiente,', 'De ahí que,'
            ]
        },
        'MOTIVATIONAL': {
            'ADDITION': [
                '¡Y eso no es todo!', 'Además,', 'También destacamos que', 'Sumado a esto,', 
                '¡Hay más buenas noticias!', 'Y ojo al dato:', 'Por si fuera poco,',
                '¡Y sigue la lista!', 'Más puntos a favor:', 'Y para sumar:', '¡Aún hay más!',
                'Y lo mejor es que', '¡Extra, extra!'
            ],
            'CONTRAST': [
                'Aún así,', 'Pero ojo,', 'Aunque tenemos el desafío de', 'Pero no nos confiemos,', 
                'Sin embargo, el reto está en', 'Aunque hay un detalle:', 'Pero atención:',
                'No obstante, cuidado con esto:', 'Aunque aquí viene el reto:', '¡Pero espera!',
                'Solo un detalle:'
            ],
            'CONCLUSION': [
                '¡Vamos por más!', 'El camino es claro:', 'Es momento de actuar:', 
                '¡A seguir empujando!', 'La meta está cerca:', '¡Manos a la obra!',
                '¡Este es el camino!', '¡A por ello!', '¡El futuro promete!', '¡A ganar!',
                '¡Sin miedo al éxito!', '¡Acción!'
            ]
        }
    }

    @staticmethod
    def assemble(parts, seed, tone='FORMAL'):
        rng = random.Random(seed)
        text = parts[0]
        tone_key = tone if tone in NarrativeBuilder.CONNECTORS else 'FORMAL'
        connectors = NarrativeBuilder.CONNECTORS[tone_key]
        
        for i in range(1, len(parts)):
            part = parts[i]
            if not part: continue
            
            # 70% probabilidad de usar conector para fluidez
            if rng.random() > 0.30: 
                lower_part = part.lower()
                # Evitar redundancia si ya tiene conector
                if any(x in lower_part for x in ['pero', 'aunque', 'sin embargo', 'obstante', 'asimismo']):
                    connector = ""
                elif i == len(parts) - 1:
                    connector = rng.choice(connectors['CONCLUSION'])
                else:
                    connector = rng.choice(connectors['ADDITION'])
                
                if connector:
                    # Ajustar mayúsculas
                    clean_part = part[0].lower() + part[1:] if len(part) > 1 else part.lower()
                    text = f"{text} {connector} {clean_part}"
                else:
                    text = f"{text} {part}"
            else:
                text = f"{text} {part}"
        return text

# --- 2. MOTORES DE ANÁLISIS ESPECÍFICOS ---

class TimelineEngine:
    @staticmethod
    def analyze_evolution(qs):
        try:
            data = qs.annotate(date=TruncDate('created_at')).values('date').annotate(count=Count('id')).order_by('date')
            labels = []; counts = []
            for entry in data:
                if entry['date']:
                    labels.append(entry['date'].strftime('%d/%m'))
                    counts.append(entry['count'])
            return {'labels': labels, 'data': counts}
        except Exception:
            return {'labels': [], 'data': []}

class NumericNarrative:
    # 1. EVALUACIÓN DE RENDIMIENTO (SATISFACCIÓN)
    TEMPLATES_PERFORMANCE = {
        'EXCELENTE': { # > 85%
            'FORMAL': {
                'fact': [
                    "El promedio es sobresaliente: {avg:.1f} / {max_val}.", "Se ha alcanzado un puntaje excepcional de {avg:.1f}.", "Los resultados rozan la perfección con un {avg:.1f}.",
                    "El indicador muestra un rendimiento superior ({avg:.1f}).", "Estamos ante un resultado de primer nivel: {avg:.1f}.", "La métrica destaca con un sólido {avg:.1f}.",
                    "Obtenemos una calificación de excelencia: {avg:.1f}.", "El puntaje {avg:.1f} supera todas las expectativas.", "Rendimiento óptimo registrado en {avg:.1f}.",
                    "La valoración es altísima: {avg:.1f} puntos.", "Liderazgo claro en esta métrica con {avg:.1f}.", "Un {avg:.1f} que denota calidad total.",
                    "El promedio {avg:.1f} es un claro indicador de éxito.", "Cifras inmejorables: {avg:.1f} sobre {max_val}.", "Máxima puntuación tendencial: {avg:.1f}."
                ],
                'meaning': [
                    "Indica una satisfacción generalizada.", "Refleja una experiencia de usuario óptima.", "Supera los estándares de calidad esperados.",
                    "Demuestra la eficacia de las estrategias actuales.", "Confirma una percepción muy positiva del servicio.", "Es una señal inequívoca de éxito.",
                    "El usuario está plenamente complacido.", "No hay fricciones relevantes en este punto.", "La propuesta de valor es contundente.",
                    "Evidencia un trabajo impecable del equipo.", "La aceptación es prácticamente total.", "El producto encaja perfectamente.",
                    "Hay una conexión emocional fuerte y positiva.", "Los usuarios son promotores activos.", "La fidelización está garantizada."
                ],
                'action': [
                    "Se recomienda mantener la estrategia actual.", "Es vital documentar qué funcionó para replicarlo.", "¡Es un caso de éxito digno de compartir!",
                    "Ideal para usar como benchmark en otras áreas.", "Sugiere reforzar y premiar al equipo responsable.", "Hay que asegurar la consistencia para no bajar este nivel.",
                    "No tocar lo que funciona, solo optimizar.", "Expandir esta práctica a otros departamentos.", "Celebrar este logro con el equipo.",
                    "Usar este dato en campañas de marketing.", "Analizar los factores de éxito para estandarizarlos.", "Proteger este estándar de calidad.",
                    "Monitorizar para evitar caídas inesperadas.", "Fidelizar a estos usuarios satisfechos.", "Convertir a estos usuarios en embajadores."
                ]
            },
            'MOTIVATIONAL': {
                'fact': [
                    "¡Increíble resultado! Alcanzamos un {avg:.1f}.", "¡Estamos en la cima! Promedio de {avg:.1f}.", "¡Qué números! Un {avg:.1f} espectacular.",
                    "¡Lo logramos! Un {avg:.1f} que brilla.", "¡Récord absoluto! {avg:.1f} de puntaje.", "¡Wow! El marcador dice {avg:.1f}.",
                    "¡Imparables! {avg:.1f} puntos.", "¡Qué orgullo! Un {avg:.1f} redondo.", "¡La rompimos! {avg:.1f} sobre {max_val}.",
                    "¡Victoria! Promedio de {avg:.1f}.", "¡Nivel leyenda! {avg:.1f}.", "¡Aplausos! Un {avg:.1f} merecido.",
                    "¡Directo al podio con {avg:.1f}!", "¡Brillante desempeño de {avg:.1f}!", "¡Superamos la meta! {avg:.1f}."
                ],
                'meaning': [
                    "El equipo está encantado con lo que estamos haciendo.", "¡La gente ama esto!", "Es una victoria clara y contundente.",
                    "Estamos conectando de verdad con la audiencia.", "Esto es música para nuestros oídos.", "¡La afición está feliz!",
                    "¡Lo estamos haciendo increíble!", "¡Nadie nos para!", "¡Somos los favoritos!",
                    "¡La comunidad está on fire!", "¡Amor puro de los usuarios!", "¡Sinergia total!",
                    "¡Esto es lo que buscábamos!", "¡Misión cumplida!", "¡El esfuerzo valió la pena!"
                ],
                'action': [
                    "¡Sigamos rompiéndola así!", "¡A celebrar y mantener el ritmo!", "¡No bajemos la guardia, vamos por el 10!",
                    "¡Es momento de presumir este logro!", "¡Que el ritmo no pare!", "¡Vamos a por más victorias como esta!",
                    "¡A por el siguiente récord!", "¡Comparte la buena noticia!", "¡Sigamos volando alto!",
                    "¡Mantengamos esa energía!", "¡A contagiar este éxito!", "¡El cielo es el límite!",
                    "¡Más fuerte que nunca!", "¡A disfrutar el triunfo!", "¡Seguimos sumando!"
                ]
            }
        },
        'BUENO': { # 70% - 85%
            'FORMAL': {
                'fact': [
                    "El desempeño es sólido con un {avg:.1f}.", "Se registra un promedio positivo de {avg:.1f}.", "El indicador muestra buena salud ({avg:.1f}).", 
                    "Puntaje favorable de {avg:.1f}.", "Resultado satisfactorio: {avg:.1f}.", "Estamos en números verdes: {avg:.1f}.",
                    "La valoración es buena ({avg:.1f}).", "Un promedio competente de {avg:.1f}.", "Cifras alentadoras: {avg:.1f}.",
                    "El nivel es adecuado ({avg:.1f}).", "Métrica estable en {avg:.1f}.", "Buen rendimiento general ({avg:.1f}).",
                    "Aceptación mayoritaria con {avg:.1f}.", "Promedio saludable de {avg:.1f}.", "Indicador robusto en {avg:.1f}."
                ],
                'meaning': [
                    "La mayoría de las respuestas son favorables.", "Estamos en zona verde, aunque con margen de mejora.", "Cumple con las expectativas básicas.", 
                    "Refleja un servicio competente.", "El usuario promedio está satisfecho.", "No hay alertas graves.",
                    "La percepción es positiva.", "El producto cumple su función.", "Hay buena recepción.",
                    "La base de usuarios está conforme.", "La estrategia funciona correctamente.", "El servicio es confiable.",
                    "Se cubren las necesidades principales.", "Hay aprobación general.", "El balance es positivo."
                ],
                'action': [
                    "Con ajustes finos se puede llegar a la excelencia.", "Identificar los puntos de fuga ayudaría a subir el nivel.", "Consolidar lo que funciona es la prioridad.", 
                    "Pequeños cambios pueden llevar esto al siguiente nivel.", "Reforzar los puntos fuertes detectados.", "Buscar la excelencia operativa.",
                    "Pulir detalles para alcanzar el 'Excelente'.", "Mantener la constancia es clave.", "No descuidar la calidad.",
                    "Atender las sugerencias menores.", "Optimizar procesos para crecer.", "Fidelizar a los usuarios satisfechos.",
                    "Investigar cómo sorprender al usuario.", "Dar el salto de calidad.", "Asegurar la sostenibilidad del resultado."
                ]
            },
            'MOTIVATIONAL': {
                'fact': [
                    "¡Buen trabajo! Un {avg:.1f} muy respetable.", "Nada mal, tenemos un {avg:.1f} sólido.", "Vamos por buen camino con este {avg:.1f}.", 
                    "¡Bien ahí! {avg:.1f} puntos.", "¡Sólido como roca! {avg:.1f}.", "¡Avanzando firme! {avg:.1f}.",
                    "¡Buen ritmo! {avg:.1f}.", "¡Positivo! {avg:.1f}.", "¡Sumando puntos! {avg:.1f}.",
                    "¡Buena racha! {avg:.1f}.", "¡Estamos bien! {avg:.1f}.", "¡Seguimos creciendo! {avg:.1f}.",
                    "¡Buen score! {avg:.1f}.", "¡Vamos bien! {avg:.1f}.", "¡Aprobado con nota! {avg:.1f}."
                ],
                'meaning': [
                    "Estamos haciendo las cosas bien.", "La base es fuerte y estable.", "Hay buena vibra en general.", 
                    "Vamos ganando terreno.", "El equipo responde bien.", "La gente confía en nosotros.",
                    "Estamos construyendo confianza.", "Hay terreno fértil.", "La dirección es la correcta.",
                    "Se nota el esfuerzo.", "Vamos progresando.", "El feedback es alentador.",
                    "Hay madera de campeones.", "La base está lista.", "Buen momentum."
                ],
                'action': [
                    "¡Un empujón más y somos excelentes!", "¡A pulir esos detalles!", "¡Sigamos construyendo sobre esto!", 
                    "¡No nos detengamos ahora!", "¡A por el nivel experto!", "¡Podemos dar más!",
                    "¡Siguiente parada: la cima!", "¡Afinar puntería!", "¡A mantener el paso!",
                    "¡Vamos por esa excelencia!", "¡A subir el listón!", "¡Que no decaiga!",
                    "¡Más energía!", "¡A perfeccionar la técnica!", "¡Adelante!"
                ]
            }
        },
        'REGULAR': { # 50% - 70%
            'FORMAL': {
                'fact': [
                    "El promedio se sitúa en un punto medio: {avg:.1f}.", "Resultado moderado de {avg:.1f}.", "El puntaje es regular ({avg:.1f}).", 
                    "Estamos en la media con un {avg:.1f}.", "Promedio estándar: {avg:.1f}.", "Valoración neutra de {avg:.1f}.",
                    "Indicador en zona gris ({avg:.1f}).", "Rendimiento promedio: {avg:.1f}.", "Calificación media de {avg:.1f}.",
                    "Ni alto ni bajo: {avg:.1f}.", "Estancado en {avg:.1f}.", "Resultado tibio ({avg:.1f}).",
                    "Promedio justo: {avg:.1f}.", "Sin destacar, {avg:.1f}.", "En el umbral aceptable: {avg:.1f}."
                ],
                'meaning': [
                    "Existen oportunidades claras de optimización.", "El grupo muestra conformidad pero no entusiasmo.", "El servicio cumple sin destacar.", 
                    "Hay margen para innovar.", "No generamos impacto suficiente.", "La experiencia es olvidable.",
                    "Falta diferenciación.", "El usuario es indiferente.", "Se cubren mínimos pero no se sorprende.",
                    "Riesgo de fuga si aparece algo mejor.", "Hay conformismo.", "Falta valor agregado.",
                    "La percepción es plana.", "No hay engagement real.", "Se cumple, pero no se enamora."
                ],
                'action': [
                    "Es recomendable revisar los puntos de dolor.", "Hay que indagar qué impide una mejor calificación.", "Se sugiere una revisión de procesos.", 
                    "Buscar diferenciadores clave es necesario.", "Necesitamos un cambio de enfoque.", "Preguntar activamente por mejoras.",
                    "Romper la inercia es vital.", "Innovar en la propuesta de valor.", "Personalizar la experiencia.",
                    "Sorprender al usuario.", "Salir de la zona de confort.", "Analizar a la competencia.",
                    "Buscar el factor 'wow'.", "Revitalizar el servicio.", "Activar palancas de satisfacción."
                ]
            },
            'MOTIVATIONAL': {
                'fact': [
                    "Estamos a mitad de tabla con un {avg:.1f}.", "Un {avg:.1f} que nos deja pensando.", "Ni bien ni mal: {avg:.1f}.", 
                    "Promedio tibio de {avg:.1f}.", "¡Empate técnico! {avg:.1f}.", "En el medio: {avg:.1f}.",
                    "Podemos más que este {avg:.1f}.", "Ahí vamos, con {avg:.1f}.", "Regular tirando a bien: {avg:.1f}.",
                    "Un {avg:.1f} para reflexionar.", "Zona de confort: {avg:.1f}.", "Tablas: {avg:.1f}.",
                    "Ni fu ni fa: {avg:.1f}.", "Estable en {avg:.1f}.", "Tranquilo en {avg:.1f}."
                ],
                'meaning': [
                    "Tenemos mucho potencial sin explotar.", "Falta esa chispa para encantar.", "Podemos hacerlo mucho mejor.", 
                    "No nos conformemos con el promedio.", "Nos falta garra.", "Estamos dormidos.",
                    "Podemos despertar pasiones.", "Falta emoción.", "Estamos en piloto automático.",
                    "Hay que sacudirse.", "El talento está, falta ejecutar.", "Podemos brillar más.",
                    "No nos representa.", "Sabemos que damos para más.", "Falta punch."
                ],
                'action': [
                    "¡Es hora de despertar y mejorar!", "¡A buscar esas oportunidades de mejora!", "¡No nos conformemos, a subir ese número!", 
                    "¡Vamos a darle la vuelta a esto!", "¡A meterle pasión!", "¡Despierta equipo!",
                    "¡A romper el molde!", "¡Salgamos de la media!", "¡A destacar!",
                    "¡Vamos por el extra!", "¡A sorprender!", "¡Cambio de marcha!",
                    "¡Acelera!", "¡Vamos a innovar!", "¡A por todas!"
                ]
            }
        },
        # ... (Agregar más variaciones para BAJO, CRITICO, POLARIZED siguiendo el mismo patrón de 15 items) ...
        'POLARIZED': {
            'FORMAL': {'fact': ["El promedio es {avg:.1f}, pero oculta una alta polarización.", "Opiniones divididas: promedio engañoso de {avg:.1f}.", "Fenómeno de polarización con media de {avg:.1f}.", "Alta varianza con media de {avg:.1f}."], 'meaning': ["Los usuarios o aman u odian la propuesta.", "Hay dos segmentos opuestos.", "Falta consistencia en la entrega."], 'action': ["Crucial segmentar para entender las diferencias.", "No guiarse solo por el promedio.", "Estandarizar la experiencia."]},
            'MOTIVATIONAL': {'fact': ["¡Guerra civil! Unos nos aman, otros no.", "Promedio de {avg:.1f}, pero opiniones extremas.", "Amor y odio en partes iguales."], 'meaning': ["Somos controversiales.", "No dejamos a nadie indiferente.", "Despertamos pasiones encontradas."], 'action': ["¡Ganemos a los detractores!", "¡Repliquemos lo que aman los fans!", "¡A unificar la experiencia!"]}
        },
        'CRITICO': {
            'FORMAL': {'fact': ["Resultado crítico: {avg:.1f}.", "Puntaje deficiente: {avg:.1f}.", "Alerta: promedio {avg:.1f} muy bajo."], 'meaning': ["Insatisfacción generalizada.", "Fallo sistémico del servicio.", "Experiencia negativa."], 'action': ["Intervención urgente requerida.", "Reevaluar estrategia ya.", "Crisis de percepción: actuar."]},
            'MOTIVATIONAL': {'fact': ["Houston, problema: {avg:.1f}.", "Duro golpe: {avg:.1f}.", "Tocamos fondo: {avg:.1f}."], 'meaning': ["Fallamos esta vez.", "Mucho dolor en usuarios.", "Inaceptable para nuestro estándar."], 'action': ["¡A reinventarnos!", "¡Aprender y renacer!", "¡Cambio radical ahora!"]}
        }
    }

    # 2. DESCRIPCIÓN DEMOGRÁFICA (EDAD, ANTIGÜEDAD, ETC.)
    TEMPLATES_DEMOGRAPHIC = {
        'DEFAULT': {
            'FORMAL': {
                'fact': [
                    "El promedio registrado es de {avg:.1f}.", "La media del grupo se sitúa en {avg:.1f}.", "El valor central estadístico es {avg:.1f}.",
                    "Se observa una media de {avg:.1f}.", "El indicador central es {avg:.1f}.", "Promedio consolidado: {avg:.1f}.",
                    "La tendencia central apunta a {avg:.1f}.", "Valor medio: {avg:.1f}.", "El dato promedio es {avg:.1f}.",
                    "Media aritmética: {avg:.1f}.", "Centro de la distribución: {avg:.1f}.", "Punto medio: {avg:.1f}.",
                    "Referencia promedio: {avg:.1f}.", "Estándar del grupo: {avg:.1f}.", "Media poblacional: {avg:.1f}."
                ],
                'context': [
                    "Los valores oscilan entre un mínimo de {min_val} y un máximo de {max_val}.", "El rango de datos abarca desde {min_val} hasta {max_val}.", "Se observa una dispersión que va de {min_val} a {max_val}.",
                    "Con extremos en {min_val} y {max_val}.", "La horquilla se sitúa entre {min_val} y {max_val}.", "Variabilidad desde {min_val} hasta {max_val}.",
                    "Cubriendo el espectro {min_val}-{max_val}.", "Desde el piso de {min_val} al techo de {max_val}.", "Rango amplio: {min_val} a {max_val}.",
                    "Intervalo observado: [{min_val}, {max_val}].", "Dispersión total entre {min_val} y {max_val}.", "Mínimo {min_val}, Máximo {max_val}.",
                    "Amplitud de {min_val} a {max_val}.", "Extremos registrados: {min_val} y {max_val}.", "Cobertura de {min_val} a {max_val}."
                ],
                'action': [
                    "Este dato permite perfilar mejor al usuario promedio del grupo.", "Es información clave para segmentar futuras acciones.", "Ayuda a calibrar el target objetivo con precisión.",
                    "Fundamental para entender la composición de la muestra.", "Base para personalizar la comunicación.", "Permite ajustar la oferta al perfil real.",
                    "Dato esencial para el diseño de producto.", "Clave para la toma de decisiones demográficas.", "Útil para comparativas de mercado.",
                    "Define el arquetipo de usuario.", "Facilita la empatía con el usuario.", "Permite modelar personas.",
                    "Ayuda a entender el contexto de uso.", "Vital para la estrategia de contenido.", "Mejora la precisión del marketing."
                ]
            },
            'MOTIVATIONAL': {
                'fact': [
                    "¡El promedio del grupo es {avg:.1f}!", "Nuestro número mágico es {avg:.1f}.", "La media es {avg:.1f}.",
                    "¡Estamos en {avg:.1f} de promedio!", "El centro es {avg:.1f}.", "¡Dato clave: {avg:.1f}!",
                    "¡Mira! {avg:.1f} de media.", "Punto de equilibrio: {avg:.1f}.", "¡Ahí lo tienes! {avg:.1f}.",
                    "¡Media confirmada: {avg:.1f}!", "¡Dato fresco: {avg:.1f}!", "¡Así somos! {avg:.1f}.",
                    "¡Nuestro perfil: {avg:.1f}!", "¡El número es {avg:.1f}!", "¡Media exacta: {avg:.1f}!"
                ],
                'context': [
                    "Tenemos gran diversidad, con participantes desde {min_val} hasta {max_val}.", "¡Hay de todo un poco! Desde {min_val} a {max_val}.", "Un espectro amplio: {min_val}-{max_val}.",
                    "¡Qué variedad! De {min_val} a {max_val}.", "Desde los {min_val} hasta los {max_val}.", "Cubrimos todo, de {min_val} a {max_val}.",
                    "¡Rango completo! {min_val} a {max_val}.", "Diversidad total: {min_val}-{max_val}.", "¡Para todos los gustos! {min_val}-{max_val}.",
                    "Amplio abanico: {min_val}-{max_val}.", "Sin límites: {min_val} a {max_val}.", "¡Qué mix! {min_val} a {max_val}.",
                    "De extremo a extremo: {min_val}-{max_val}.", "¡Todos cuentan! {min_val}-{max_val}.", "¡Gran cobertura! {min_val}-{max_val}."
                ],
                'action': [
                    "¡Es genial conocer mejor quiénes somos!", "¡La diversidad nos enriquece!", "¡Dato clave para conocernos!",
                    "¡Aprovechemos esta variedad!", "¡Qué grupo tan interesante!", "¡Información es poder!",
                    "¡Conocernos es el primer paso!", "¡A sacar provecho de esto!", "¡Qué buenos datos!",
                    "¡Esto nos define!", "¡Orgullosos de nuestra gente!", "¡A conectar con todos!",
                    "¡Entender es clave!", "¡Sigamos descubriendo!", "¡Qué buen insight!"
                ]
            }
        },
        'CONCENTRATED': {
            'FORMAL': {'fact': ["La media se sitúa en {avg:.1f}, con una baja dispersión."], 'context': ["El grupo es bastante homogéneo, concentrándose la mayoría cerca del promedio."], 'action': ["Esta uniformidad facilita diseñar estrategias estandarizadas."]},
            'MOTIVATIONAL': {'fact': ["¡Estamos muy sintonizados! Promedio de {avg:.1f}."], 'context': ["La mayoría del grupo comparte características muy similares."], 'action': ["¡Un equipo compacto y coherente!"]}
        }
    }

    @staticmethod
    def _is_highly_polarized(stats_dist, max_val, total):
        if not stats_dist or total < 5: return False
        low_limit = max_val / 3
        high_limit = max_val * (2/3)
        low_votes = sum(d['count'] for d in stats_dist if d['value'] <= low_limit)
        high_votes = sum(d['count'] for d in stats_dist if d['value'] >= high_limit)
        return (low_votes / total) > 0.25 and (high_votes / total) > 0.25

    @staticmethod
    def analyze(avg, max_val, min_val=0, stats_dist=None, tone='FORMAL', is_demographic=False):
        if not max_val or max_val == 0: return f"Promedio registrado: {avg:.1f}."
        total = sum(d['count'] for d in stats_dist) if stats_dist else 0
        rng = random.Random(str(avg) + str(max_val) + str(total))

        if is_demographic:
            key = 'DEFAULT'
            if max_val - min_val < (avg * 0.2): key = 'CONCENTRATED'
            base_block = NumericNarrative.TEMPLATES_DEMOGRAPHIC[key]
            tone_templates = base_block.get(tone, base_block['FORMAL'])
            return NarrativeBuilder.assemble([
                rng.choice(tone_templates['fact']).format(avg=avg, max_val=max_val, min_val=min_val),
                rng.choice(tone_templates['context']).format(avg=avg, max_val=max_val, min_val=min_val),
                rng.choice(tone_templates['action'])
            ], int(avg*100), tone)

        pct = (avg / max_val) * 100
        key = 'REGULAR'
        if NumericNarrative._is_highly_polarized(stats_dist, max_val, total): key = 'POLARIZED'
        elif pct >= 85: key = 'EXCELENTE'
        elif pct <= 40: key = 'CRITICO'
        elif pct >= 70: key = 'BUENO'
        elif pct >= 50: key = 'REGULAR'
        elif pct >= 30: key = 'BAJO'
        
        base_block = NumericNarrative.TEMPLATES_PERFORMANCE.get(key, NumericNarrative.TEMPLATES_PERFORMANCE['REGULAR'])
        tone_templates = base_block.get(tone, base_block['FORMAL'])
        
        return NarrativeBuilder.assemble([
            rng.choice(tone_templates['fact']).format(avg=avg, max_val=max_val),
            rng.choice(tone_templates['meaning']),
            rng.choice(tone_templates['action'])
        ], int(avg*100), tone)

class DemographicNarrative:
    # 3. CATEGÓRICO (>100 Variaciones)
    TEMPLATES = {
        'UNANIMOUS': {
            'FORMAL': {
                'fact': ["Existe un consenso casi absoluto: la opción **{top1}** domina con un {pct1:.1f}%.", "La opción **{top1}** concentra la inmensa mayoría ({pct1:.1f}%).", "Hegemonía total de **{top1}**, acaparando el {pct1:.1f}%."],
                'context': ["La preferencia del grupo es clara e indiscutible frente a las alternativas.", "No existe competencia real; la decisión es unánime.", "El alineamiento del grupo en este punto es total."],
                'action': ["Esta homogeneidad facilita la toma de decisiones enfocada en esta opción.", "Permite avanzar sin fricciones en esta dirección.", "Confirma que la estrategia actual es la correcta."]
            },
            'MOTIVATIONAL': {
                'fact': ["¡Todos a una! **{top1}** arrasa con el {pct1:.1f}% de los votos.", "¡Victoria aplastante! **{top1}** se lleva el {pct1:.1f}%.", "¡Sin discusión! **{top1}** es el rey ({pct1:.1f}%)."],
                'context': ["Es raro ver al equipo tan alineado, ¡genial!", "¡Sinergia pura! Todos piensan igual.", "¡Qué maravilla de consenso!"],
                'action': ["No hay dudas: el camino es por aquí.", "¡Aceleren a fondo en esa dirección!", "¡Aprovechemos esta unión para avanzar rápido!"]
            }
        },
        'DOMINANT': {
            'FORMAL': {
                'fact': ["**{top1}** lidera las preferencias con un {pct1:.1f}%.", "Mayoría clara para **{top1}** ({pct1:.1f}%).", "La opción **{top1}** destaca con el {pct1:.1f}%."],
                'context': ["Aunque hay otras opciones en juego, la tendencia es clara.", "Se perfila como la favorita del grupo.", "Marca la pauta principal de la encuesta."],
                'action': ["Es seguro priorizar esta opción, sin descuidar a las minorías.", "Recomendamos enfocar recursos aquí.", "Validar esta preferencia con acciones concretas."]
            },
            'MOTIVATIONAL': {
                'fact': ["Tenemos un favorito claro: **{top1}** se lleva el {pct1:.1f}%.", "**{top1}** va ganando la carrera ({pct1:.1f}%).", "El público aclama a **{top1}** ({pct1:.1f}%)."],
                'context': ["La balanza se inclina favorablemente hacia este lado.", "¡Buen viento para esta opción!", "La tendencia es nuestra amiga."],
                'action': ["¡Es una apuesta segura!", "¡Sigamos esa estrella!", "¡A darle con todo a la opción ganadora!"]
            }
        },
        'DUAL': {
            'FORMAL': {
                'fact': [
                    "Las opiniones están divididas principalmente entre **{top1}** ({pct1:.1f}%) y **{top2}**.", "Escenario bipolar: **{top1}** frente a **{top2}**.", "La audiencia se fragmenta en dos bloques: **{top1}** y **{top2}**.",
                    "Competencia cerrada: **{top1}** ({pct1:.1f}%) vs **{top2}**.", "Dos opciones dominan el panorama: **{top1}** y **{top2}**.", "Empate técnico virtual entre **{top1}** y **{top2}**.",
                    "Preferencia dual: **{top1}** ({pct1:.1f}%) y **{top2}** lideran.", "El grupo oscila entre **{top1}** y **{top2}**.", "Fuerte polarización hacia **{top1}** y **{top2}**.",
                    "Disputa principal entre **{top1}** ({pct1:.1f}%) y **{top2}**.", "Atención dividida: **{top1}** y **{top2}**.", "Dos claros contendientes: **{top1}** y **{top2}**.",
                    "La elección está entre **{top1}** ({pct1:.1f}%) y **{top2}**.", "No hay monopolio: **{top1}** y **{top2}** comparten protagonismo.", "Dicotomía clara: **{top1}** vs **{top2}**."
                ],
                'context': [
                    "No hay un líder único; la audiencia muestra dos perfiles de preferencia claros.", "La polarización es evidente y significativa.", "Ambas opciones tienen un peso considerable en la decisión.",
                    "El grupo no se decanta por una sola vía.", "Existen dos necesidades o visiones distintas conviviendo.", "La diversidad de opinión es binaria.",
                    "Refleja dos segmentos de usuarios bien diferenciados.", "No se puede ignorar a ninguna de las dos partes.", "Hay un equilibrio de fuerzas.",
                    "La competencia es intensa entre estas variantes.", "Se observan dos tendencias contrapuestas o paralelas.", "El consenso es parcial.",
                    "Ambas propuestas resuenan con fuerza.", "Hay validación para ambos caminos.", "La decisión no es obvia."
                ],
                'action': [
                    "Sería estratégico considerar soluciones que atiendan a ambos segmentos.", "Se requiere una estrategia diferenciada para cada grupo.", "Buscar un punto medio integrador sería ideal.",
                    "No descartar ninguna opción prematuramente.", "Evaluar si es posible ofrecer ambas alternativas.", "Profundizar en qué motiva cada elección.",
                    "Segmentar la comunicación según esta preferencia.", "Desarrollar propuestas de valor duales.", "Realizar A/B testing para desempatar.",
                    "Evitar alienar a uno de los grupos.", "Buscar sinergias entre ambas opciones.", "Priorizar según el objetivo estratégico, sabiendo que hay renuncia.",
                    "Mantener ambas líneas abiertas si los recursos lo permiten.", "Investigar si hay un tercer camino que una a ambos.", "Tomar una decisión informada asumiendo el coste de oportunidad."
                ]
            },
            'MOTIVATIONAL': {
                'fact': [
                    "¡Duelo de titanes! La cosa está reñida entre **{top1}** ({pct1:.1f}%) y **{top2}**.", "¡Final de fotografía! **{top1}** vs **{top2}**.", "¡Qué batalla! Empate casi técnico.",
                    "¡Divididos! **{top1}** y **{top2}** pelean la cima.", "¡Dos grandes favoritos! **{top1}** y **{top2}**.", "¡Mano a mano! **{top1}** ({pct1:.1f}%) contra **{top2}**."
                ],
                'context': [
                    "¡El grupo no se decide!", "¡Emoción hasta el final!", "¡Dos grandes opciones compitiendo!",
                    "¡Hay pasión en ambos bandos!", "¡Nadie quiere ceder!", "¡Qué interesante debate!"
                ],
                'action': [
                    "¡Qué interesante diversidad!", "¡A contentar a ambos bandos!", "¡Doble desafío, doble diversión!",
                    "¡A jugar con dos cartas!", "¡Que ganen los dos!", "¡A ser creativos para unirnos!"
                ]
            }
        },
        'FRAGMENTED': {
            'FORMAL': {'fact': ["Alta dispersión; el top es **{top1}** con solo {pct1:.1f}%.", "Resultados muy atomizados."], 'context': ["Indica gran diversidad de perfiles."], 'action': ["Investigar patrones subyacentes."]},
            'MOTIVATIONAL': {'fact': ["¡Para gustos, colores!", "¡Lluvia de opiniones!"], 'context': ["¡Qué riqueza de perspectivas!"], 'action': ["¡Toca ser muy flexibles!"]}
        }
    }
    
    @staticmethod
    def analyze(dist, total, tone='FORMAL'):
        if not dist: return "Datos insuficientes."
        sorted_dist = sorted(dist, key=lambda x: x['count'], reverse=True)
        top1 = sorted_dist[0]
        top1_pct = (top1['count'] / total) * 100
        top2 = sorted_dist[1] if len(sorted_dist) > 1 else None
        top2_pct = (top2['count'] / total) * 100 if top2 else 0
        
        key = 'FRAGMENTED'
        if top1_pct >= 70: key = 'UNANIMOUS'
        elif top1_pct >= 50: key = 'DOMINANT'
        elif top2 and (top1_pct - top2_pct) < 15: key = 'DUAL'
        
        base_block = DemographicNarrative.TEMPLATES.get(key, DemographicNarrative.TEMPLATES['FRAGMENTED'])
        tone_block = base_block.get(tone, base_block['FORMAL'])
        rng = random.Random(str(total) + top1['option'])
        
        return NarrativeBuilder.assemble([
            rng.choice(tone_block['fact']).format(top1=top1['option'], pct1=top1_pct, top2=top2['option'] if top2 else ''),
            rng.choice(tone_block['context']),
            rng.choice(tone_block['action'])
        ], int(top1_pct), tone)

class TextNarrative:
    # 4. TEXTO ABIERTO (>100 Variaciones)
    TEMPLATES = {
        'INTRO': {
            'FORMAL': [
                "Se han analizado en profundidad {count} comentarios.", "Tras revisar el contenido de {count} respuestas,", "El análisis cualitativo de {count} opiniones revela patrones interesantes.",
                "Procesando el feedback de {count} usuarios,", "Basado en la lectura de {count} entradas,", "El estudio de {count} testimonios indica que:",
                "Se examinaron {count} menciones.", "Del total de {count} comentarios recibidos,", "La minería de texto sobre {count} respuestas muestra:"
            ],
            'MOTIVATIONAL': [
                "¡Leímos atentamente las {count} respuestas!", "La voz del usuario se hizo escuchar en {count} comentarios.", "Feedback de {count} personas procesado:",
                "¡{count} personas nos contaron su historia!", "¡Tenemos {count} opiniones valiosas!", "Escuchamos a {count} usuarios y esto dicen:"
            ]
        },
        'TOPIC': {
            'FORMAL': [
                "El tema predominante en la conversación es **{topic}**.", "Los usuarios centran su atención principalmente en **{topic}**.", "Se destaca **{topic}** como el eje central de las discusiones.",
                "La palabra clave más recurrente es **{topic}**.", "Existe una preocupación notable sobre **{topic}**.", "El concepto de **{topic}** se repite constantemente."
            ],
            'MOTIVATIONAL': [
                "¡Todo el mundo habla de **{topic}**!", "El tema del momento es, sin duda, **{topic}**.", "**{topic}** está en boca de todos.",
                "¡**{topic}** es la estrella del show!", "¡No paran de mencionar **{topic}**!", "¡El foco está en **{topic}**!"
            ]
        },
        'SENTIMENT_LINK': {
            'Positivo': ["Afortunadamente, la percepción al respecto es muy buena.", "Lo cual ha generado una respuesta favorable.", "Y las noticias son buenas:"],
            'Negativo': ["Lamentablemente, esto genera fricción.", "Sin embargo, es aquí donde surgen las mayores quejas.", "Lo que ha detonado críticas recurrentes."],
            'Neutral': ["Las opiniones al respecto son variadas.", "No hay un consenso claro sobre esto.", "Generando debate con puntos de vista mixtos."]
        },
        'CONCLUSION': {
            'Positivo': ["En resumen, el tono es alentador.", "Predomina la satisfacción.", "Hay que mantener este rumbo."],
            'Negativo': ["Se detectan áreas críticas de mejora.", "El sentimiento general tiende a ser negativo.", "Es prioritario atender estas inquietudes."],
            'Neutral': ["El feedback está balanceado.", "Es un escenario de opiniones encontradas.", "Hay oportunidades tanto de mejora como de consolidación."]
        }
    }
    @staticmethod
    def generate(count, topics, sentiment, quote=None, tone='FORMAL'):
        rng = random.Random(count + len(topics))
        intro = rng.choice(TextNarrative.TEMPLATES['INTRO'].get(tone, TextNarrative.TEMPLATES['INTRO']['FORMAL'])).format(count=count)
        topic_part = ""
        if topics:
            topic_part = rng.choice(TextNarrative.TEMPLATES['TOPIC'].get(tone, TextNarrative.TEMPLATES['TOPIC']['FORMAL'])).format(topic=topics[0])
        else:
            topic_part = "Los temas tratados son muy diversos."
        link_part = rng.choice(TextNarrative.TEMPLATES['SENTIMENT_LINK'].get(sentiment, [""]))
        concl_part = rng.choice(TextNarrative.TEMPLATES['CONCLUSION'].get(sentiment, [""]))
        
        full_text = f"{intro} {topic_part} {link_part}"
        if quote:
            connector = "Un usuario comentó:" if tone == 'FORMAL' else "Mira lo que dicen:"
            full_text += f" {connector} _{quote}_."
        full_text += f" {concl_part}"
        return full_text

class TextMiningEngine:
    POSITIVE_WORDS = {'bien', 'bueno', 'excelente', 'genial', 'mejor', 'feliz', 'satisfecho', 'gracias', 'encanta', 'perfecto', 'amable', 'rapido', 'eficiente', 'util', 'facil', 'seguro'}
    NEGATIVE_WORDS = {'mal', 'malo', 'pésimo', 'peor', 'horrible', 'lento', 'difícil', 'error', 'problema', 'queja', 'sucio', 'caro', 'tarde', 'pesimo', 'feo', 'inutil', 'complicado', 'falla'}
    @staticmethod
    def extract_topics_and_sentiment(texts):
        if not texts: return [], "Neutral"
        words = []
        pos_count = 0; neg_count = 0
        for text in texts:
            clean = TextMiningEngine.normalize_text(text)
            tokens = [w for w in clean.split() if len(w) > 3]
            words.extend(tokens)
            for w in tokens:
                if w in TextMiningEngine.POSITIVE_WORDS: pos_count += 1
                elif w in TextMiningEngine.NEGATIVE_WORDS: neg_count += 1
        total_sent = pos_count + neg_count
        sentiment_label = "Neutral"
        if total_sent > 0:
            score = (pos_count - neg_count) / total_sent
            if score > 0.15: sentiment_label = "Positivo"
            elif score < -0.15: sentiment_label = "Negativo"
        return ([item[0] for item in Counter(words).most_common(6)] if words else []), sentiment_label
    @staticmethod
    def normalize_text(text):
        if not text: return ''
        return re.sub(r'[^a-z0-9\s]', '', unicodedata.normalize('NFKD', str(text).lower()).encode('ascii', 'ignore').decode('ascii'))
    @staticmethod
    def find_representative_quote(texts, topic):
        if not topic: return None
        for text in texts:
            if topic in text.lower() and 20 < len(text) < 110: return f'"{text}"'
        return None

# --- 3. SERVICIO PRINCIPAL ---

class SurveyAnalysisService:
    @staticmethod
    def _optimize_chart_data(raw_dist, is_numeric=False):
        if not raw_dist: return [], []
        if is_numeric:
            data_points = []
            for d in raw_dist:
                if d.get('value') is not None:
                    data_points.extend([float(d['value'])] * d['count'])
            if not data_points: return [], []
            unique_vals = set(data_points)
            if len(unique_vals) <= 12:
                sorted_dist = sorted(raw_dist, key=lambda x: x['value'])
                labels = [str(int(d['value']) if d['value'] % 1 == 0 else d['value']) for d in sorted_dist]
                data = [d['count'] for d in sorted_dist]
                return labels, data
            min_val = min(data_points); max_val = max(data_points)
            num_bins = 10
            interval = (max_val - min_val) / num_bins
            if interval < 1: interval = 1
            ranges = []; curr = min_val
            for _ in range(num_bins):
                end = curr + interval
                ranges.append((curr, end))
                curr = end
            bins_count = [0] * num_bins
            for val in data_points:
                for i, (start, end) in enumerate(ranges):
                    if start <= val < end or (i == num_bins-1 and start <= val <= end + 0.1):
                        bins_count[i] += 1; break
            final_labels = []; final_data = []
            for i, count in enumerate(bins_count):
                if count > 0:
                    start, end = ranges[i]
                    lbl = f"{int(start)}-{int(end)}" if int(start) != int(end) else str(int(start))
                    final_labels.append(lbl); final_data.append(count)
            return final_labels, final_data
        else:
            sorted_dist = sorted(raw_dist, key=lambda x: x['count'], reverse=True)
            if len(sorted_dist) <= 9: return [d['option'] for d in sorted_dist], [d['count'] for d in sorted_dist]
            top_8 = sorted_dist[:8]
            others = sorted_dist[8:]
            return [d['option'] for d in top_8] + ["Otros"], [d['count'] for d in top_8] + [sum(d['count'] for d in others)]

    @staticmethod
    @staticmethod
    async def get_analysis_data(survey, responses_queryset, include_charts=None, cache_key=None, config=None):
        config = config or {}
        tone = config.get('tone', 'FORMAL').upper()
        include_quotes = config.get('include_quotes', True)
        
        if cache_key is None:
            total = await sync_to_async(responses_queryset.count)()
            last_id = await sync_to_async(lambda: responses_queryset.order_by('-id').values_list('id', flat=True).first() or 0)()
            cache_key = f"analysis_v20_ultra:{survey.id}:{total}:{last_id}:{tone}:{include_quotes}"
            
        cached = cache.get(cache_key)
        if cached: return cached

        questions = await sync_to_async(lambda: list(survey.questions.prefetch_related('options').order_by('order')))()
        analyzable_q = [q for q in questions if q.type != 'section']

        numeric_stats, numeric_dist = await SurveyAnalysisService._fetch_numeric_stats(analyzable_q, responses_queryset)
        choice_dist = await SurveyAnalysisService._fetch_choice_stats(analyzable_q, responses_queryset)
        text_responses = await SurveyAnalysisService._fetch_text_responses(analyzable_q, responses_queryset)
        
        analysis_data = []
        satisfaction_values = []
        main_satisfaction_qid = next((q.id for q in analyzable_q if q.type in ['scale', 'number']), None)

        for idx, q in enumerate(analyzable_q, 1):
            item = {
                'id': q.id, 'text': q.text, 'type': q.type, 'order': idx,
                'insight': '', 'insight_data': {}, 'total_respuestas': 0,
                'chart_labels': [], 'chart_data': [], 'opciones': [],
                'tipo_display': None, 'samples_texto': [], 'chart': None,
                'top_responses': []
            }

            if q.id in numeric_stats:
                st = numeric_stats[q.id]
                raw_dist = numeric_dist.get(q.id, [])
                item.update(st)
                item['total_respuestas'] = st.get('count', 0)
                if q.id == main_satisfaction_qid:
                    for d in raw_dist:
                        if d['value'] is not None: satisfaction_values.extend([d['value']] * d['count'])
                
                item['chart_labels'], item['chart_data'] = SurveyAnalysisService._optimize_chart_data(raw_dist, is_numeric=True)
                item['tipo_display'] = 'bar'
                
                is_demo = getattr(q, 'is_demographic', False) or (q.text and 'edad' in q.text.lower())
                narrative = NumericNarrative.analyze(st['avg'], st['max'], min_val=st['min'], stats_dist=raw_dist, tone=tone, is_demographic=is_demo)
                item['insight'] = narrative
                item['insight_data'] = {'type': 'numeric', 'average': st['avg'], 'max': st['max'], 'min': st['min'], 'narrative': narrative, 'key_insight': narrative}
                if item['chart_labels']:
                    # Generar gráfico Plotly interactivo
                    from core.utils.charts import ChartGenerator
                    item['chart'] = ChartGenerator.generate_horizontal_bar_chart_plotly(
                        item['chart_labels'], item['chart_data'], title=None, dark_mode=False
                    )

            elif q.id in text_responses:
                texts = text_responses[q.id]
                topics, sentiment = TextMiningEngine.extract_topics_and_sentiment(texts)
                item['total_respuestas'] = len(texts)
                item['top_responses'] = texts[:5]
                item['samples_texto'] = texts[:5]
                item['tipo_display'] = 'text'
                quote = None
                if include_quotes and topics: quote = TextMiningEngine.find_representative_quote(texts, topics[0])
                full_narrative = TextNarrative.generate(len(texts), topics, sentiment, quote, tone)
                item['insight'] = full_narrative
                item['insight_data'] = {'type': 'text', 'narrative': full_narrative, 'key_insight': full_narrative, 'topics': topics}

            elif q.id in choice_dist:
                raw_dist = choice_dist[q.id]
                total_q = sum(d['count'] for d in raw_dist)
                item['total_respuestas'] = total_q
                item['chart_labels'], item['chart_data'] = SurveyAnalysisService._optimize_chart_data(raw_dist, is_numeric=False)
                item['opciones'] = [{'label': d['option'], 'count': d['count'], 'percent': (d['count']/total_q)*100 if total_q else 0} for d in raw_dist]
                chart_type = 'bar' if len(item['chart_labels']) > 4 else 'doughnut'
                item['tipo_display'] = chart_type
                narrative = DemographicNarrative.analyze(raw_dist, total_q, tone=tone)
                item['insight'] = narrative
                item['insight_data'] = {'type': 'categorical', 'narrative': narrative, 'key_insight': narrative}
                if item['chart_labels']:
                    from core.utils.charts import ChartGenerator
                    if chart_type == 'bar':
                        item['chart'] = ChartGenerator.generate_horizontal_bar_chart_plotly(
                            item['chart_labels'], item['chart_data'], title=None, dark_mode=False
                        )
                    else:
                        item['chart'] = ChartGenerator.generate_doughnut_chart_plotly(
                            item['chart_labels'], item['chart_data'], title=None, dark_mode=False
                        )

            analysis_data.append(item)

        kpi = round(sum(satisfaction_values)/len(satisfaction_values), 1) if satisfaction_values else 0
        evolution = await sync_to_async(TimelineEngine.analyze_evolution)(responses_queryset)
        result = {
            'analysis_data': analysis_data, 'kpi_prom_satisfaccion': kpi,
            'nps_data': {'score': None}, 'heatmap_image': None, 'total_respuestas': await sync_to_async(responses_queryset.count)(),
            'evolution': evolution
        }
        cache.set(cache_key, result, 3600)
        return result

    @staticmethod
    @staticmethod
    async def _fetch_numeric_stats(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type in ['scale', 'number']]
        if not ids: return {}, {}
        valid = QuestionResponse.objects.filter(question_id__in=ids, survey_response__in=qs, numeric_value__isnull=False)
        stats_qs = await sync_to_async(lambda: list(valid.values('question_id').annotate(cnt=Count('id'), avg=Avg('numeric_value'), max_val=Max('numeric_value'), min_val=Min('numeric_value'))))()
        stats = {x['question_id']: {'count': x['cnt'], 'avg': float(x['avg']), 'max': x['max_val'], 'min': x['min_val']} for x in stats_qs}
        dist = defaultdict(list)
        dist_qs = await sync_to_async(lambda: list(valid.values('question_id', 'numeric_value').annotate(cnt=Count('id'))))()
        for x in dist_qs: dist[x['question_id']].append({'value': x['numeric_value'], 'count': x['cnt']})
        return stats, dist

    @staticmethod
    @staticmethod
    async def _fetch_choice_stats(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type in ['single', 'multi', 'radio', 'select']]
        if not ids: return {}
        dist = defaultdict(list)
        dist_qs = await sync_to_async(lambda: list(QuestionResponse.objects.filter(question_id__in=ids, survey_response__in=qs).values('question_id', 'selected_option__text').annotate(cnt=Count('id'))))()
        for x in dist_qs:
            if x['selected_option__text']: dist[x['question_id']].append({'option': x['selected_option__text'], 'count': x['cnt']})
        return dist

    @staticmethod
    @staticmethod
    async def _fetch_text_responses(analyzable_q, qs):
        ids = [q.id for q in analyzable_q if q.type == 'text']
        if not ids: return {}
        res = defaultdict(list)
        try:
            res_qs = await sync_to_async(lambda: list(QuestionResponse.objects.filter(question_id__in=ids, survey_response__in=qs).exclude(text_value='').values('question_id', 'text_value').order_by('-created_at')[:200]))()
        except Exception:
            res_qs = await sync_to_async(lambda: list(QuestionResponse.objects.filter(question_id__in=ids, survey_response__in=qs).exclude(text_value='').values('question_id', 'text_value')[:200]))()
        for x in res_qs: res[x['question_id']].append(x['text_value'])
        return res
    
    @staticmethod
    def generate_crosstab(survey, row_id, col_id, queryset=None):
        return {'error': 'Crosstab requiere dataframe builder.'}