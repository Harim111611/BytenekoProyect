# Surveys Responses Templates - Respondiendo Encuestas

Este subdirectorio contiene templates para el flujo de responder encuestas públicamente.

## Archivos

- **fill.html**: Formulario para responder encuesta
- **thanks.html**: Página de agradecimiento post-respuesta
- **results.html**: Resultados de la encuesta respondida

## fill.html

Formulario público para responder:
- Preguntas de la encuesta
- Campos de entrada según tipo
- Validación en tiempo real
- Indicador de progreso

```html
<!DOCTYPE html>
<html>
<head>
  <title>{{ survey.title }}</title>
</head>
<body>
  <div class="survey-container">
    <div class="survey-header">
      <h1>{{ survey.title }}</h1>
      <p>{{ survey.description }}</p>
      <div class="progress">
        <div class="progress-bar" style="width: 0%"></div>
      </div>
    </div>
    
    <form method="post" id="survey-form">
      {% csrf_token %}
      
      {% for question in survey.questions.all %}
        <div class="question" data-question-id="{{ question.id }}">
          <h3>{{ question.text }}</h3>
          
          {% if question.question_type == 'text' %}
            <input type="text" name="q{{ question.id }}" required>
          
          {% elif question.question_type == 'choice' %}
            {% for option in question.options.all %}
              <label>
                <input type="radio" name="q{{ question.id }}" value="{{ option.id }}" required>
                {{ option.text }}
              </label>
            {% endfor %}
          
          {% elif question.question_type == 'rating' %}
            <div class="rating">
              {% for i in "12345" %}
                <input type="radio" name="q{{ question.id }}" value="{{ i }}">
              {% endfor %}
            </div>
          
          {% endif %}
        </div>
      {% endfor %}
      
      <button type="submit" class="btn-primary">Enviar Respuestas</button>
    </form>
  </div>
{% endblock %}

{% block extra_js %}
  <script src="{% static 'js/survey-response.js' %}"></script>
{% endblock %}
```

## thanks.html

Página post-respuesta:
- Mensaje de agradecimiento
- Opción de compartir
- Enlace a encuestas relacionadas
- Tiempo de redirección

```html
{% extends "base/base.html" %}

{% block title %}¡Gracias!{% endblock %}

{% block content %}
  <div class="thanks-page">
    <div class="success-icon">✓</div>
    <h1>¡Gracias por tu respuesta!</h1>
    <p>Tus respuestas han sido guardadas correctamente.</p>
    
    <div class="actions">
      <a href="{% url 'index' %}" class="btn">Volver al inicio</a>
      <button class="btn" onclick="window.print()">Imprimir confirmación</button>
    </div>
  </div>
  
  <script>
    // Redireccionar después de 10 segundos
    setTimeout(function() {
      window.location = '{% url "index" %}';
    }, 10000);
  </script>
{% endblock %}
```

## results.html

Ver resultados de encuesta:
- Gráficos de distribución
- Estadísticas
- Comparativas
- Exportación

## Context

```python
context = {
    'survey': survey,
    'questions': questions,
}

# Para results:
context = {
    'survey': survey,
    'responses': responses,
    'stats': statistics,
    'charts': chart_data,
}
```

## Seguridad

- CSRF token en formulario
- Validación de datos
- Limitación de respuestas por IP (opcional)
- No requiere login

## Performance

- Caché de encuesta
- Lazy load de gráficos
- Compresión de CSS/JS
- Minificación

## UX

- Indicador de progreso
- Validación en tiempo real
- Indicación de campos requeridos
- Mensajes de error claros
