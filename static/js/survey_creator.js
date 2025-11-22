/* static/js/survey_creator.js */

document.addEventListener('DOMContentLoaded', function() {

    let currentStep = 1;
    let questionCount = 0;

    // --- REFERENCIAS A TU DISEÑO (IDs) ---
    const btnStep1Next = document.getElementById('btn-next-1');
    const btnStep2Prev = document.getElementById('btn-to-step-1-from-2');
    const btnNext2 = document.getElementById('btn-next-2');
    const btnPrev3 = document.getElementById('btn-to-step-2-from-3');
    const btnAddQuestion = document.getElementById('btn-add-custom-question');
    const btnPublish = document.getElementById('btn-publish');

    const stepCards = [
        document.getElementById('card-step-1'),
        document.getElementById('card-step-2'),
        document.getElementById('card-step-3')
    ];

    const stepContents = [
        document.getElementById('step-1-content'),
        document.getElementById('step-2-content'),
        document.getElementById('step-3-content')
    ];

    const progressBar = document.getElementById('progressBar');
    const percentCounter = document.getElementById('percentCounter');
    const stepCounter = document.getElementById('stepCounter');

    // --- EVENTOS ---
    if(btnStep1Next) btnStep1Next.addEventListener('click', () => validateAndGo(2));
    if(btnStep2Prev) btnStep2Prev.addEventListener('click', () => goToStep(1));
    if(btnNext2) btnNext2.addEventListener('click', () => validateAndGo(3));
    if(btnPrev3) btnPrev3.addEventListener('click', () => goToStep(2));
    if(btnAddQuestion) btnAddQuestion.addEventListener('click', addQuestion);
    if(btnPublish) btnPublish.addEventListener('click', submitSurvey);

    // Iniciar el Wizard en el Paso 1
    goToStep(1);

    function goToStep(step) {
        // 1. Ocultar y mostrar contenido
        stepContents.forEach(el => el.classList.add('d-none'));
        stepContents[step-1].classList.remove('d-none');

        // 2. Actualizar estilos de tarjetas
        const totalSteps = 3;
        stepCards.forEach((card, index) => {
            card.classList.remove('active', 'completed');
            if (index + 1 < step) card.classList.add('completed');
            if (index + 1 === step) card.classList.add('active');
        });

        // 3. Actualizar barra de progreso
        const percent = step === 1 ? 33 : (step === 2 ? 66 : 100);
        if(progressBar) progressBar.style.width = `${percent}%`;
        if(stepCounter) stepCounter.innerText = `Paso ${step} de 3`;
        if(percentCounter) percentCounter.innerText = `${percent}% completado`;

        currentStep = step;
    }

    function validateAndGo(targetStep) {
        // Validaciones Paso 1
        if (targetStep === 2) {
            const title = document.getElementById('surveyTitle').value.trim();
            const category = document.getElementById('surveyCategory').value.trim();

            if (!title) return alert('Falta el título.');
            if (!category) return alert('Falta la categoría.');
        }

        // Validaciones Paso 2
        if (targetStep === 3) {
            const qItems = document.querySelectorAll('.question-item');
            if (qItems.length === 0) return alert('Agrega al menos una pregunta.');

            let valid = true;
            qItems.forEach(q => {
                // Validación: la pregunta debe tener título
                if(!q.querySelector('.question-title').value.trim()) valid = false;
            });
            if (!valid) return alert('Completa los textos de las preguntas.');

            // Generar el HTML de vista previa
            renderPreview();
        }

        goToStep(targetStep);
    }

    function addQuestion() {
        questionCount++;
        const container = document.getElementById('questions-list');
        const template = document.getElementById('questionTemplate');

        if (!container || !template) return;

        const clone = template.content.cloneNode(true);

        // Asignar número de pregunta
        clone.querySelector('.question-number').textContent = `Pregunta ${questionCount}`;

        // IDs únicos para el checkbox
        const uid = `req_${Date.now()}_${Math.random().toString(36).substr(2,5)}`;
        const check = clone.querySelector('.question-required');
        const label = clone.querySelector('.form-check-label');

        if (check) check.id = uid;
        if (label) label.setAttribute('for', uid);

        // Eventos internos de la tarjeta
        const typeSelect = clone.querySelector('.question-type');
        const optsDiv = clone.querySelector('.options-container');

        typeSelect.addEventListener('change', function() {
            if(['single', 'multi'].includes(this.value)) {
                optsDiv.classList.remove('d-none');
                setTimeout(() => optsDiv.querySelector('input').focus(), 100);
            } else {
                optsDiv.classList.add('d-none');
            }
        });

        // Botón Eliminar
        clone.querySelector('.btn-close').addEventListener('click', function() {
            this.closest('.question-item').remove();
        });

        container.appendChild(clone);

        // Auto-focus y scroll
        setTimeout(() => {
            const newCard = container.lastElementChild;
            if(newCard) {
                newCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                newCard.querySelector('.question-title').focus();
            }
        }, 100);
    }

    // --- FUNCIÓN DE VISTA PREVIA ---
    function renderPreview() {
        // 1. Info General
        const title = document.getElementById('surveyTitle').value;
        const desc = document.getElementById('surveyDescription').value;
        const cat = document.getElementById('surveyCategory').value;

        // Inyectar al resumen
        document.getElementById('review-title').innerText = title;
        document.getElementById('review-category').innerText = cat;

        // Inyectar al simulador (encabezado)
        document.getElementById('preview-header-title').innerText = title;
        document.getElementById('preview-header-desc').innerText = desc || 'Sin descripción';

        // 2. Preguntas
        const container = document.getElementById('preview-container');
        if (!container) return; // Asegurar que el contenedor existe

        container.innerHTML = ''; // Limpiar

        const qEls = document.querySelectorAll('.question-item');
        document.getElementById('review-count').innerText = qEls.length;

        qEls.forEach((el, idx) => {
            const qTitle = el.querySelector('.question-title').value;
            const qType = el.querySelector('.question-type').value;
            const isReq = el.querySelector('.question-required').checked;

            const card = document.createElement('div');
            card.className = 'preview-card p-3 mb-2';

            let inputHTML = '';
            const requiredSpan = isReq ? '<span class="text-danger">*</span>' : '';

            // Generación de Inputs Dinámicos para la Preview
            if (qType === 'text') {
                inputHTML = `<textarea class="form-control bg-body-tertiary border-0" rows="2" disabled></textarea>`;
            } else if (qType === 'number') {
                inputHTML = `<input type="number" class="form-control bg-body-tertiary border-0" disabled placeholder="0">`;
            } else if (qType === 'scale') {
                // Simulación de escala 0-10
                inputHTML = `<div class="d-flex gap-1 justify-content-between">
                    ${[...Array(11).keys()].map(i => `<div class="border rounded text-center py-1 px-2 small bg-body-tertiary text-muted" style="flex:1;">${i}</div>`).join('')}
                </div>`;
            } else if (qType === 'single' || qType === 'multi') {
                const optsText = el.querySelector('.question-options').value;
                const opts = optsText.split(',').map(s => s.trim()).filter(s => s);
                const typeAttr = qType === 'single' ? 'radio' : 'checkbox';

                inputHTML = opts.map(opt => `
                    <div class="form-check">
                        <input class="form-check-input" type="${typeAttr}" disabled>
                        <label class="form-check-label small">${opt || 'Opción'}</label>
                    </div>
                `).join('');
            }

            card.innerHTML = `
                <label class="form-label fw-bold small text-body-emphasis mb-2">
                    ${idx + 1}. ${qTitle} ${requiredSpan}
                </label>
                ${inputHTML}
            `;
            container.appendChild(card);
        });
    }

    function submitSurvey() {
        const surveyData = {
            surveyInfo: {
                titulo: document.getElementById('surveyTitle').value,
                descripcion: document.getElementById('surveyDescription').value,
                categoria: document.getElementById('surveyCategory').value
            },
            questions: []
        };

        document.querySelectorAll('.question-item').forEach(el => {
            const type = el.querySelector('.question-type').value;
            const qData = {
                titulo: el.querySelector('.question-title').value,
                tipo: type,
                required: el.querySelector('.question-required').checked
            };
            if (['single', 'multi'].includes(type)) {
                qData.opciones = el.querySelector('.question-options').value.split(',').map(s => s.trim()).filter(s => s);
            }
            surveyData.questions.push(qData);
        });

        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        fetch('/surveys/crear/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify(surveyData)
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) window.location.href = data.redirect_url;
            else alert('Error: ' + data.error);
        })
        .catch(() => alert('Error de conexión.'));
    }
});