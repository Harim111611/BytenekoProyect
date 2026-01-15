// Example frontend JS to enqueue fast delete and poll task status

async function enqueueDeleteSurvey(surveyId) {
  if (!confirm('Esto eliminará permanentemente la encuesta y todas sus respuestas. Escribe OK para continuar.')) return;

  const resp = await fetch(`/surveys/api/${surveyId}/delete-enqueue/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken'),
    },
    body: JSON.stringify({}),
  });

  const data = await resp.json();
  if (!data.success) {
    alert('Error: ' + (data.error || 'unknown'));
    return;
  }

  const taskId = data.task_id;
  // Poll for status
  const interval = setInterval(async () => {
    const st = await fetch(`/surveys/api/task-status/${taskId}/`);
    const sd = await st.json();
    console.log(sd);
    if (sd.state === 'SUCCESS' || sd.state === 'FAILURE' || sd.state === 'REVOKED') {
      clearInterval(interval);
      if (sd.result && sd.result.success) {
        alert('Encuesta eliminada correctamente');
        window.location.href = '/surveys/';
      } else {
        alert('La eliminación finalizó con error: ' + JSON.stringify(sd.result));
      }
    }
  }, 2000);
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
