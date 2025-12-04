/**
 * Motor de acciones asíncronas para Byteneko
 * Maneja Importación Múltiple y Borrado sin recargar la página.
 */

const AsyncManager = {
    // --- BORRADO ---
    deleteSurvey: async function(surveyId, publicId, btnElement) {
        if (!confirm('¿Estás seguro? Esto eliminará la encuesta y todas sus respuestas permanentemente.')) return;

        // UI: Poner el botón en estado de carga
        const originalText = btnElement.innerText;
        btnElement.disabled = true;
        btnElement.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Borrando...';

        try {
            // 1. Solicitar borrado
            const response = await fetch(`/surveys/delete/${publicId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            const data = await response.json();

            if (data.success) {
                // 2. Iniciar Polling del Task
                this.pollTaskStatus(data.task_id, () => {
                    // Éxito: Eliminar la fila de la tabla visualmente
                    const row = document.getElementById(`survey-row-${surveyId}`);
                    if (row) {
                        row.style.transition = 'all 0.5s';
                        row.style.opacity = '0';
                        setTimeout(() => row.remove(), 500);
                    }
                    showToast('success', 'Encuesta eliminada correctamente');
                }, (errorMsg) => {
                    alert('Error al borrar: ' + errorMsg);
                    btnElement.disabled = false;
                    btnElement.innerText = originalText;
                });
            } else {
                throw new Error(data.error || 'Error desconocido');
            }
        } catch (error) {
            console.error(error);
            alert('Error de conexión');
            btnElement.disabled = false;
            btnElement.innerText = originalText;
        }
    },

    // --- IMPORTACIÓN ---
    uploadFiles: async function(formElement, resultContainerId) {
        const formData = new FormData(formElement);
        const resultContainer = document.getElementById(resultContainerId);
        resultContainer.innerHTML = '<div class="alert alert-info"><span class="spinner-border spinner-border-sm"></span> Subiendo archivos...</div>';
        
        try {
            // 1. Subir Archivos
            const response = await fetch(formElement.action, {
                method: 'POST',
                body: formData,
                headers: {'X-Requested-With': 'XMLHttpRequest'}
            });
            const data = await response.json();

            if (data.success) {
                // Si es un solo job (legacy) o lista de jobs
                const jobs = data.jobs || [{job_id: data.job_id, filename: 'Archivo'}];
                
                // Renderizar barras de progreso
                let html = '<div class="mt-3">';
                jobs.forEach(job => {
                    html += `
                        <div class="mb-2" id="job-card-${job.job_id}">
                            <div class="d-flex justify-content-between">
                                <small>${job.filename}</small>
                                <small id="status-text-${job.job_id}">Procesando...</small>
                            </div>
                            <div class="progress" style="height: 5px;">
                                <div id="progress-${job.job_id}" class="progress-bar progress-bar-striped progress-bar-animated" style="width: 100%"></div>
                            </div>
                        </div>`;
                });
                html += '</div>';
                resultContainer.innerHTML = html;

                // 2. Polling para cada archivo
                jobs.forEach(job => {
                    this.pollImportStatus(job.job_id);
                });

            } else {
                resultContainer.innerHTML = `<div class="alert alert-danger">Error: ${data.error}</div>`;
            }
        } catch (error) {
            resultContainer.innerHTML = `<div class="alert alert-danger">Error de red: ${error}</div>`;
        }
    },

    // --- POLLING HELPERS ---
    pollTaskStatus: function(taskId, onSuccess, onError) {
        const interval = setInterval(async () => {
            const resp = await fetch(`/surveys/delete-task/${taskId}/status/`);
            const data = await resp.json();

            if (data.status === 'SUCCESS') {
                clearInterval(interval);
                onSuccess();
            } else if (data.status === 'FAILURE' || data.status === 'REVOKED') {
                clearInterval(interval);
                onError(data.error || 'Falló la tarea');
            }
        }, 1000); // Chequear cada 1s
    },

    pollImportStatus: function(jobId) {
        const interval = setInterval(async () => {
            const resp = await fetch(`/surveys/import-job/${jobId}/status/`);
            const data = await resp.json();
            
            const statusText = document.getElementById(`status-text-${jobId}`);
            const progressBar = document.getElementById(`progress-${jobId}`);

            if (data.status === 'completed') {
                clearInterval(interval);
                statusText.innerText = '✅ Completado';
                statusText.classList.add('text-success');
                progressBar.classList.remove('progress-bar-striped', 'progress-bar-animated');
                progressBar.classList.add('bg-success');
                
                // Opcional: Recargar página si todos completados
                if (document.querySelectorAll('.bg-success').length === document.querySelectorAll('.progress-bar').length) {
                    setTimeout(() => window.location.href = "/surveys/", 1000);
                }

            } else if (data.status === 'failed') {
                clearInterval(interval);
                statusText.innerText = '❌ Error';
                statusText.classList.add('text-danger');
                progressBar.classList.add('bg-danger');
                // Mostrar mensaje de error
                const card = document.getElementById(`job-card-${jobId}`);
                card.innerHTML += `<small class="text-danger d-block">${data.error_message}</small>`;
            }
        }, 1500);
    }
};

// Helper para CSRF
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