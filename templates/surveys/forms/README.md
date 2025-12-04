# Surveys Forms Templates - Formularios de Encuestas

Este subdirectorio contiene templates para formularios de creación y edición.

## Archivos

- **form.html**: Formulario genérico de preguntas
- **survey_create.html**: Formulario de creación de encuesta

## survey_create.html

Formulario para crear nueva encuesta:
- Campos: título, descripción
- Selector de tipo
- Preguntas iniciales
- JavaScript para agregar preguntas dinámicamente

```html
{% extends "base/base.html" %}

{% block title %}Crear Encuesta{% endblock %}

{% block content %}
  <div class="survey-form">
    <h1>Nueva Encuesta</h1>
    
    <form method="post" id="survey-form">
      {% csrf_token %}
      
      <div class="form-group">
        <label for="title">Título</label>
        <input type="text" id="title" name="title" required>
      </div>
      
      <div class="form-group">
        <label for="description">Descripción</label>
        <textarea id="description" name="description"></textarea>
      </div>
      
      <div class="questions-section">
        <h3>Preguntas</h3>
        <div id="questions-container">
          <!-- Preguntas agregadas dinámicamente -->
        </div>
        <button type="button" onclick="addQuestion()">+ Agregar Pregunta</button>
      </div>
      
      <button type="submit" class="btn-primary">Crear Encuesta</button>
    </form>
  </div>
{% endblock %}

{% block extra_js %}
  <script src="{% static 'js/survey-builder.js' %}"></script>
{% endblock %}
```

## form.html

Formulario genérico para preguntas:
- Tipo de pregunta (text, choice, rating)
- Opciones de respuesta
- Validaciones
- Preview

## Componentes

### Pregunta Genérica
```html
<div class="question-item" data-question-id="{{ question.id }}">
  <input type="text" placeholder="Pregunta" value="{{ question.text }}">
  
  <select name="question_type">
    <option value="text">Texto</option>
    <option value="choice">Opción múltiple</option>
    <option value="rating">Escala</option>
  </select>
  
  <button onclick="removeQuestion(this)">Eliminar</button>
</div>
```

### Opciones de Respuesta
```html
<div class="options">
  {% for option in question.options.all %}
    <input type="text" value="{{ option.text }}">
  {% endfor %}
  <button type="button" onclick="addOption()">+ Opción</button>
</div>
```

## JavaScript Interactivo

Survey builder:
- Agregar/eliminar preguntas
- Cambiar tipos de pregunta
- Preview en tiempo real
- Validación cliente

## Context

```python
context = {
    'form': survey_form,
    'survey': survey,  # Para edición
    'questions': questions,
}
```

## AJAX

Guardar automáticamente:
```javascript
$('#survey-form').on('change', function() {
  // Auto-save
  saveProgress();
});
```

## Validación

Client-side:
- Título requerido
- Al menos una pregunta
- Validar opciones

Server-side:
- Longitud máxima
- Caracteres permitidos
- Lógica de negocio
