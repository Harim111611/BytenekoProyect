// static/surveys/js/async_actions.js

const AsyncManager = {
    deleteSurvey: function(surveyId, publicId, btn) {
        if (!confirm('¿Seguro que deseas borrar esta encuesta?')) return;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
        
        fetch(`/surveys/${publicId}/delete/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': AsyncManager.getCSRF(),
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
        .then(resp => resp.json())
        .then(data => {
            if (data.task_id) {
                AsyncManager.pollDeleteStatus(data.task_id, surveyId, btn);
            } else if (data.success) {
                // fallback: borrado inmediato
                AsyncManager.removeRow(surveyId);
            } else {
                alert(data.error || 'Error al borrar');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-trash"></i>';
            }
        })
        .catch(() => {
            alert('Error de red');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-trash"></i>';
        });
    },
    pollDeleteStatus: function(taskId, surveyId, btn) {
        let poll = setInterval(() => {
            fetch(`/surveys/delete-task-status/${taskId}/`)
                .then(resp => resp.json())
                .then(data => {
                    if (data.status === 'SUCCESS' || data.status === 'SUCCESSFUL' || data.status === 'COMPLETED') {
                        clearInterval(poll);
                        AsyncManager.removeRow(surveyId);
                    } else if (data.status === 'FAILURE' || data.error) {
                        clearInterval(poll);
                        alert('Error al borrar: ' + (data.error || 'Desconocido'));
                        btn.disabled = false;
                        btn.innerHTML = '<i class="bi bi-trash"></i>';
                    }
                })
                .catch(() => {
                    clearInterval(poll);
                    alert('Error de red al consultar estado de borrado');
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-trash"></i>';
                });
        }, 1000);
    },
    removeRow: function(surveyId) {
        let row = document.getElementById(`survey-row-${surveyId}`);
        if (row) row.remove();
    },
    uploadFiles: function(form, resultDivId) {
        let formData = new FormData(form);
        let btn = form.querySelector('button[type="submit"]');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Importando...';
        let resultDiv = document.getElementById(resultDivId);
        resultDiv.innerHTML = '<div class="text-info">Subiendo archivos...</div>';
        fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        })
        .then(resp => resp.json())
        .then(data => {
            if (data.jobs) {
                resultDiv.innerHTML = '<ul id="importJobList"></ul>';
                data.jobs.forEach(job => {
                    let li = document.createElement('li');
                    li.id = `import-job-${job.job_id}`;
                    li.innerHTML = `<b>${job.filename}</b>: <span class="badge bg-warning">Pendiente</span>`;
                    document.getElementById('importJobList').appendChild(li);
                    AsyncManager.pollImportStatus(job.job_id, li.id);
                });
            } else if (data.job_id) {
                // Un solo archivo
                let li = document.createElement('div');
                li.id = `import-job-${data.job_id}`;
                li.innerHTML = `<span class="badge bg-warning">Pendiente</span>`;
                resultDiv.appendChild(li);
                AsyncManager.pollImportStatus(data.job_id, li.id);
            } else {
                resultDiv.innerHTML = `<div class="text-danger">${data.error || 'Error inesperado'}</div>`;
            }
            btn.disabled = false;
            btn.innerHTML = 'Importar';
        })
        .catch(() => {
            resultDiv.innerHTML = '<div class="text-danger">Error de red</div>';
            btn.disabled = false;
            btn.innerHTML = 'Importar';
        });
    },
    pollImportStatus: function(jobId, elementId) {
        let poll = setInterval(() => {
            fetch(`/surveys/import/status/${jobId}/`)
                .then(resp => resp.json())
                .then(data => {
                    let el = document.getElementById(elementId);
                    if (!el) { clearInterval(poll); return; }
                    if (data.status === 'completed') {
                        el.innerHTML = `<span class="badge bg-success">Completado</span> (${data.processed_rows || 0} filas)`;
                        clearInterval(poll);
                    } else if (data.status === 'failed') {
                        el.innerHTML = `<span class="badge bg-danger">Fallido</span> ${data.error_message || ''}`;
                        clearInterval(poll);
                    } else if (data.status === 'processing') {
                        el.innerHTML = `<span class="badge bg-info">Procesando...</span>`;
                    }
                })
                .catch(() => {
                    let el = document.getElementById(elementId);
                    if (el) el.innerHTML = '<span class="badge bg-danger">Error de red</span>';
                    clearInterval(poll);
                });
        }, 1000);
    },
    getCSRF: function() {
        let name = 'csrftoken';
        let cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            let c = cookies[i].trim();
            if (c.startsWith(name + '=')) {
                return decodeURIComponent(c.substring(name.length + 1));
            }
        }
        return '';
    }
};
