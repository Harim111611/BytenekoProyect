# Surveys CRUD Templates - Operaciones CRUD de Encuestas

Este subdirectorio contiene templates para operaciones básicas de Create, Read, Update, Delete.

## Archivos

- **list.html**: Listado de encuestas
- **detail.html**: Detalles de encuesta
- **encuesta_detail.html**: Detalles alternativo
- **confirm_delete.html**: Confirmación de eliminación
- **not_found.html**: Encuesta no encontrada

## list.html

Listado de encuestas del usuario:
- Tabla con encuestas
- Acciones (ver, editar, eliminar)
- Paginación
- Búsqueda/filtros

```html
{% extends "base/base.html" %}

{% block title %}Mis Encuestas{% endblock %}

{% block content %}
  <div class="surveys-list">
    <h1>Mis Encuestas</h1>
    <a href="{% url 'surveys:create' %}" class="btn">Crear Nueva</a>
    
    <table class="surveys-table">
      <thead>
        <tr>
          <th>Título</th>
          <th>Estado</th>
          <th>Respuestas</th>
          <th>Acciones</th>
        </tr>
      </thead>
      <tbody>
        {% for survey in surveys %}
          <tr>
            <td>{{ survey.title }}</td>
            <td>{{ survey.get_status_display }}</td>
            <td>{{ survey.responses_count }}</td>
            <td>
              <a href="{% url 'surveys:detail' survey.id %}">Ver</a>
              <a href="{% url 'surveys:edit' survey.id %}">Editar</a>
              <a href="{% url 'surveys:delete' survey.id %}">Eliminar</a>
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
    
    <!-- Paginación -->
  </div>
{% endblock %}
```

## detail.html

Detalles de una encuesta:
- Información general
- Preguntas y opciones
- Estadísticas
- Acciones disponibles

## encuesta_detail.html

Detalles alternativos (Legacy):
- Versión anterior del template
- Posibilidad de migrar a detail.html

## confirm_delete.html

Confirmación antes de eliminar:
- Mensaje de advertencia
- Información a eliminar
- Botones Confirmar/Cancelar

```html
{% extends "base/base.html" %}

{% block title %}Confirmar Eliminación{% endblock %}

{% block content %}
  <div class="confirm-delete">
    <h2>¿Eliminar encuesta?</h2>
    <p>{{ survey.title }}</p>
    <p class="warning">Esta acción no se puede deshacer.</p>
    
    <form method="post">
      {% csrf_token %}
      <button type="submit" class="btn-danger">Eliminar</button>
      <a href="{% url 'surveys:detail' survey.id %}" class="btn-secondary">Cancelar</a>
    </form>
  </div>
{% endblock %}
```

## not_found.html

Encuesta no existe:
- Mensaje claro
- Botón para volver
- Sugerencias

## Context

```python
context = {
    'survey': survey,
    'questions': questions,
    'stats': statistics,
}
```

## Seguridad

- Solo el propietario puede ver/editar
- CSRF token en formularios
- Validación en backend
