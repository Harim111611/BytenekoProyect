# Surveys Components Templates - Componentes Reutilizables

Este subdirectorio contiene componentes HTML/CSS/JS reutilizables para las vistas de encuestas.

## Archivos

- **_toast_delete.html**: Notificación toast para eliminación
- **_toast_feedback.html**: Notificación toast para feedback

## _toast_delete.html

Componente de notificación emergente para acciones de eliminación:

```html
<div class="toast toast-delete" id="toastDelete">
  <div class="toast-content">
    <span class="toast-icon">🗑️</span>
    <div class="toast-text">
      <p class="toast-title">Eliminado</p>
      <p class="toast-message" id="toastDeleteMessage">Encuesta eliminada correctamente</p>
    </div>
    <button class="toast-close" onclick="closeToast('toastDelete')">&times;</button>
  </div>
  <div class="toast-progress"></div>
</div>
```

### Uso

```html
{% include "surveys/components/_toast_delete.html" %}

<script>
function deleteItem(id) {
  fetch(`/surveys/${id}/delete/`, { method: 'DELETE' })
    .then(() => showToast('toastDelete', 'Encuesta eliminada'))
    .catch(err => showToast('toastDelete', 'Error al eliminar'));
}
</script>
```

## _toast_feedback.html

Componente de notificación para feedback general:

```html
<div class="toast toast-feedback" id="toastFeedback">
  <div class="toast-content">
    <span class="toast-icon">ℹ️</span>
    <div class="toast-text">
      <p class="toast-title">Información</p>
      <p class="toast-message" id="toastFeedbackMessage"></p>
    </div>
    <button class="toast-close" onclick="closeToast('toastFeedback')">&times;</button>
  </div>
  <div class="toast-progress"></div>
</div>
```

### Uso

```html
{% include "surveys/components/_toast_feedback.html" %}

<script>
function showSuccessMessage(message) {
  showToast('toastFeedback', message);
}
</script>
```

## Estilos Base

```css
.toast {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  min-width: 300px;
  animation: slideIn 0.3s ease-out;
  z-index: 999;
}

.toast-content {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.toast-icon {
  font-size: 24px;
  flex-shrink: 0;
}

.toast-delete {
  border-left: 4px solid #dc3545;
}

.toast-feedback {
  border-left: 4px solid #0d6efd;
}

.toast-progress {
  height: 3px;
  background: linear-gradient(to right, currentColor, transparent);
  animation: progress 3s linear forwards;
}

@keyframes slideIn {
  from {
    transform: translateX(400px);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

@keyframes progress {
  from { width: 100%; }
  to { width: 0%; }
}
```

## JavaScript Utilidades

```javascript
// Mostrar toast
function showToast(elementId, message) {
  const toast = document.getElementById(elementId);
  const messageEl = toast.querySelector('.toast-message');
  
  if (message) {
    messageEl.textContent = message;
  }
  
  toast.style.display = 'block';
  
  setTimeout(() => {
    closeToast(elementId);
  }, 3000);
}

// Cerrar toast
function closeToast(elementId) {
  const toast = document.getElementById(elementId);
  toast.style.display = 'none';
}

// Variantes de toast
function showDeleteToast(itemName) {
  showToast('toastDelete', `${itemName} eliminado correctamente`);
}

function showSuccessToast(message) {
  showToast('toastFeedback', message);
}

function showErrorToast(message) {
  const toast = document.getElementById('toastFeedback');
  toast.classList.remove('toast-feedback');
  toast.classList.add('toast-error');
  showToast('toastFeedback', message);
}
```

## Inclusión en Templates

En templates padre que necesiten componentes toast:

```html
{% extends "base/base.html" %}

{% block content %}
  <!-- Contenido -->
  
  {% include "surveys/components/_toast_delete.html" %}
  {% include "surveys/components/_toast_feedback.html" %}
{% endblock %}
```

## Variantes de Estilo

### success
```css
.toast-success {
  border-left: 4px solid #198754;
}
```

### error
```css
.toast-error {
  border-left: 4px solid #dc3545;
}
```

### warning
```css
.toast-warning {
  border-left: 4px solid #ffc107;
}
```

## Accesibilidad

- Role="alert" para screen readers
- Tecla ESC para cerrar
- Color + íconos para información visual
- Suficiente contraste de color

## Performance

- Componentes ligeros (sin dependencias)
- Auto-dismiss después de 3s
- Transiciones suaves con GPU acceleration
- Clickeable para cerrar manualmente
