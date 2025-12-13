// Frontend JS to enqueue fast delete and poll task status
// Corrected to use the proper endpoints and handle Celery UUIDs

async function enqueueDeleteSurvey(surveyId) {
  if (!confirm('Esta acción eliminará permanentemente la encuesta y todas sus respuestas. ¿Continuar?')) return;

  // 1. Solicitar el borrado al endpoint correcto (SurveyDeleteView)
  // Nota: surveyId aquí debe ser el 'public_id' si así lo espera la URL, o ID numérico si usas PK.
  // Basado en urls.py: path("<str:public_id>/delete/", ...) espera public_id.
  const resp = await fetch(`/surveys/${surveyId}/delete/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
      'X-Requested-With': 'XMLHttpRequest' // CRÍTICO: Para recibir JSON en lugar de HTML
    },
    body: JSON.stringify({}),
  });

  const data = await resp.json();
  if (!data.success) {
    alert('Error: ' + (data.error || 'Error desconocido al iniciar borrado'));
    return;
  }

  const taskId = data.task_id;
  console.log(`[Delete] Tarea iniciada: ${taskId}`);

  // 2. Poll for status usando el endpoint correcto para Tareas Celery
  // FIX: Usar /delete-task/.../status/ que maneja UUIDs, no /task_status/ que es para Imports
  const interval = setInterval(async () => {
    try {
        const st = await fetch(`/surveys/delete-task/${taskId}/status/`);
        
        if (!st.ok) {
            console.error("Error polling status:", st.status);
            return;
        }

        const sd = await st.json();
        console.log("Poll status:", sd);

        // La vista delete_task_status devuelve 'status' (UPPERCASE), no 'state'
        const state = sd.status; 

        if (state === 'SUCCESS' || state === 'FAILURE' || state === 'REVOKED') {
          clearInterval(interval);
          
          // Verificar resultado lógico
          if (state === 'SUCCESS') {
            // El backend devuelve success: true dentro de 'result' o directamente en la respuesta base
            // Adaptar según crud_views.py -> delete_task_status
            alert('Encuesta eliminada correctamente.');
            window.location.href = '/surveys/';
          } else {
            alert('Error al eliminar: ' + (sd.error || 'Fallo en la tarea'));
          }
        }
    } catch (e) {
        console.error("Network error polling:", e);
    }
  }, 1000);
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}