# Surveys Modals Templates - Diálogos Modales

Este subdirectorio contiene templates para diálogos modales de confirmación y acciones.

## Archivos

- **delete_all_modal.html**: Modal para eliminar todas las encuestas
- **delete_one_modal.html**: Modal para eliminar una encuesta
- **delete_selected_modal.html**: Modal para eliminar seleccionadas

## delete_one_modal.html

Modal para confirmación de eliminación individual:
- Nombre de la encuesta
- Advertencia
- Botones Confirmar/Cancelar

```html
<div class="modal" id="deleteOneModal">
  <div class="modal-content">
    <div class="modal-header">
      <h2>Eliminar Encuesta</h2>
      <button class="close" onclick="closeModal()">&times;</button>
    </div>
    
    <div class="modal-body">
      <p>¿Estás seguro de que deseas eliminar?</p>
      <p class="survey-name" id="surveyName"></p>
      <p class="warning">⚠️ Esta acción no se puede deshacer.</p>
    </div>
    
    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeModal()">Cancelar</button>
      <button class="btn-danger" onclick="confirmDelete()">Eliminar</button>
    </div>
  </div>
</div>
```

## delete_all_modal.html

Modal para eliminar todas las encuestas:
- Listado de encuestas a eliminar
- Contador
- Confirmación múltiple

```html
<div class="modal" id="deleteAllModal">
  <div class="modal-content">
    <div class="modal-header">
      <h2>Eliminar Todas las Encuestas</h2>
    </div>
    
    <div class="modal-body">
      <p>Se eliminarán <strong id="surveyCount">0</strong> encuestas:</p>
      <ul id="surveyList">
        <!-- Lista dinámicamente -->
      </ul>
      <p class="warning">⚠️ Esto incluye todos los datos y respuestas.</p>
    </div>
    
    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeModal()">Cancelar</button>
      <button class="btn-danger" onclick="confirmDeleteAll()">Eliminar Todas</button>
    </div>
  </div>
</div>
```

## delete_selected_modal.html

Modal para eliminar seleccionadas:
- Checkboxes de selección
- Preview de seleccionadas
- Confirmación

## Estilos Base

```css
.modal {
  display: none;
  position: fixed;
  z-index: 1000;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0,0,0,0.5);
}

.modal-content {
  background-color: white;
  margin: 10% auto;
  padding: 20px;
  border: 1px solid #ddd;
  width: 80%;
  max-width: 500px;
}
```

## JavaScript

Mostrar/ocultar modal:
```javascript
function openDeleteModal(surveyId, surveyName) {
  document.getElementById('surveyName').textContent = surveyName;
  document.getElementById('deleteOneModal').style.display = 'block';
  window.currentSurveyId = surveyId;
}

function closeModal() {
  document.getElementById('deleteOneModal').style.display = 'none';
}

function confirmDelete() {
  // Enviar request DELETE
  fetch(`/surveys/${window.currentSurveyId}/delete/`, {
    method: 'DELETE',
    headers: {
      'X-CSRFToken': getCookie('csrftoken')
    }
  }).then(() => {
    window.location.reload();
  });
}
```

## Inclusión en Templates

```html
{% include "surveys/modals/delete_one_modal.html" %}
```

## Accesibilidad

- Focus trap en modal
- Tecla ESC para cerrar
- ARIA labels
- Keyboard navigation
