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
    const btnSuggestQuestions = document.getElementById('btn-suggest-questions');
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
    if(btnSuggestQuestions) btnSuggestQuestions.addEventListener('click', suggestQuestions);
    if(btnPublish) btnPublish.addEventListener('click', submitSurvey);

    // --- IMPORTACIÓN CSV ---
    const importForm = document.getElementById('importCsvForm');
    if(importForm) {
        if(importForm) importForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const btn = importForm.querySelector('button[type="submit"]');
            btn.disabled = true;
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Importando...';
            const formData = new FormData(importForm);
            try {
                const resp = await fetch(importForm.action, {method: 'POST', body: formData});
                const data = await resp.json();
                if(data.success) {
                    showToast('✅ Importación completada', 'success');
                    setTimeout(() => window.location.reload(), 1200);
                } else {
                    showToast(data.error || 'Error en importación', 'danger');
                }
            } catch {
                showToast('Error de red', 'danger');
            }
            btn.disabled = false;
            btn.innerHTML = originalText;
        });
    }

    // --- BULK DELETE ---
    const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
    if(bulkDeleteBtn) {
        if(bulkDeleteBtn) bulkDeleteBtn.addEventListener('click', async function() {
            if(this.disabled) return;
            const checked = Array.from(document.querySelectorAll('.survey-checkbox:checked')).map(cb => cb.value);
            if(!checked.length) return showToast('Selecciona al menos una encuesta', 'warning');
            if(!confirm(`¿Seguro que quieres eliminar ${checked.length} encuestas y todas sus respuestas?`)) return;
            this.disabled = true;
            const original = this.innerHTML;
            this.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Eliminando...';
            try {
                const resp = await fetch('/surveys/bulk-delete/', {
                    method: 'POST',
                    headers: {'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value, 'X-Requested-With': 'XMLHttpRequest'},
                    body: new URLSearchParams(checked.map(id => ['survey_ids', id]))
                });
                const data = await resp.json();
                if(data.success) {
                    showToast(`✅ Eliminadas ${data.deleted} encuestas`, 'success');
                    setTimeout(() => window.location.reload(), 1200);
                } else {
                    showToast(data.error || 'Error al eliminar', 'danger');
                }
            } catch {
                showToast('Error de red', 'danger');
            }
            this.disabled = false;
            this.innerHTML = original;
        });
    }

    // --- TOAST FEEDBACK ---
    function showToast(msg, type) {
        let toast = document.getElementById('mainToast');
        if(!toast) {
            toast = document.createElement('div');
            toast.id = 'mainToast';
            toast.className = 'toast align-items-center text-bg-' + (type||'info') + ' border-0 position-fixed bottom-0 end-0 m-3';
            toast.style.zIndex = 9999;
            toast.innerHTML = `<div class="d-flex"><div class="toast-body"></div><button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
            document.body.appendChild(toast);
        }
        toast.querySelector('.toast-body').textContent = msg;
        toast.className = 'toast align-items-center text-bg-' + (type||'info') + ' border-0 position-fixed bottom-0 end-0 m-3';
        const bsToast = bootstrap.Toast.getOrCreateInstance(toast, {delay: 3000});
        bsToast.show();
    }

    // Iniciar el Wizard en el Paso 1
    goToStep(1);

    // --- TEMPLATES DE PREGUNTAS SUGERIDAS POR CATEGORÍA ---
    const questionTemplates = {
        'satisfaccion': [
            { texto: '¿Qué tan satisfecho estás con nuestro producto/servicio?', tipo: 'scale', required: true },
            { texto: '¿Qué tan probable es que recomiendes nuestro producto/servicio a un amigo o colega?', tipo: 'scale', required: true },
            { texto: '¿Qué es lo que más te gusta de nuestro producto/servicio?', tipo: 'text', required: false },
            { texto: '¿Qué podríamos mejorar?', tipo: 'text', required: false },
            { texto: '¿Con qué frecuencia utilizas nuestro producto/servicio?', tipo: 'single', opciones: ['Diariamente', 'Semanalmente', 'Mensualmente', 'Raramente'], required: true }
        ],
        'mercado': [
            { texto: '¿Cuál es tu rango de edad?', tipo: 'single', opciones: ['18-24', '25-34', '35-44', '45-54', '55+'], required: true },
            { texto: '¿Cuál es tu nivel de ingresos mensual?', tipo: 'single', opciones: ['Menos de $500', '$500-$1000', '$1000-$2000', '$2000-$5000', 'Más de $5000'], required: false },
            { texto: '¿Qué factores son más importantes para ti al comprar este tipo de producto?', tipo: 'multi', opciones: ['Precio', 'Calidad', 'Marca', 'Recomendaciones', 'Disponibilidad'], required: true },
            { texto: 'En una escala del 1 al 10, ¿qué tan importante es la sostenibilidad ambiental en tus decisiones de compra?', tipo: 'scale', required: true },
            { texto: '¿Qué otras marcas consideras al hacer esta compra?', tipo: 'text', required: false }
        ],
        'rrhh': [
            { texto: '¿Qué tan satisfecho estás con tu ambiente de trabajo actual?', tipo: 'scale', required: true },
            { texto: '¿Te sientes valorado en tu puesto de trabajo?', tipo: 'scale', required: true },
            { texto: '¿Qué aspectos de tu trabajo te gustaría que mejoraran?', tipo: 'multi', opciones: ['Salario', 'Beneficios', 'Balance vida-trabajo', 'Oportunidades de crecimiento', 'Cultura organizacional', 'Herramientas y tecnología'], required: true },
            { texto: '¿Qué tan probable es que sigas trabajando aquí en los próximos 12 meses?', tipo: 'scale', required: true },
            { texto: '¿Tienes algún comentario o sugerencia adicional?', tipo: 'text', required: false }
        ],
        'educacion': [
            { texto: '¿Qué tan satisfecho estás con la calidad de la enseñanza?', tipo: 'scale', required: true },
            { texto: '¿Los materiales y recursos proporcionados son adecuados?', tipo: 'scale', required: true },
            { texto: '¿Qué aspectos del curso/programa te gustaría mejorar?', tipo: 'multi', opciones: ['Contenido', 'Metodología', 'Evaluaciones', 'Comunicación', 'Recursos digitales'], required: true },
            { texto: '¿Qué tan útil ha sido este curso para tu desarrollo profesional?', tipo: 'scale', required: true },
            { texto: 'Comparte cualquier comentario adicional', tipo: 'text', required: false }
        ],
        'producto': [
            { texto: '¿Qué tan fácil fue usar nuestro producto?', tipo: 'scale', required: true },
            { texto: '¿El producto cumplió con tus expectativas?', tipo: 'scale', required: true },
            { texto: '¿Qué características te gustaría que añadiéramos?', tipo: 'text', required: false },
            { texto: '¿Qué tan probable es que vuelvas a comprar este producto?', tipo: 'scale', required: true },
            { texto: '¿Cómo calificarías la relación calidad-precio?', tipo: 'scale', required: true }
        ],
        'tecnologia': [
            { texto: '¿Qué tan satisfecho estás con la interfaz de usuario?', tipo: 'scale', required: true },
            { texto: '¿Has experimentado algún problema técnico?', tipo: 'single', opciones: ['Sí, frecuentemente', 'Sí, ocasionalmente', 'Raramente', 'Nunca'], required: true },
            { texto: '¿Qué funcionalidades utilizas más?', tipo: 'multi', opciones: ['Dashboard', 'Reportes', 'Configuración', 'Integraciones', 'Análisis'], required: true },
            { texto: '¿Qué tan intuitiva encuentras la plataforma?', tipo: 'scale', required: true },
            { texto: '¿Qué mejoras sugerirías?', tipo: 'text', required: false }
        ],
        'evento': [
            { texto: '¿Qué tan satisfecho estás con la organización del evento?', tipo: 'scale', required: true },
            { texto: '¿Cómo calificarías la calidad del contenido presentado?', tipo: 'scale', required: true },
            { texto: '¿Qué aspecto del evento te gustó más?', tipo: 'multi', opciones: ['Ponentes', 'Networking', 'Logística', 'Ubicación', 'Catering', 'Materiales'], required: true },
            { texto: '¿El evento cumplió con tus expectativas?', tipo: 'single', opciones: ['Superó expectativas', 'Cumplió expectativas', 'Estuvo bien', 'No cumplió expectativas'], required: true },
            { texto: '¿Qué recomendarías mejorar para futuros eventos?', tipo: 'text', required: false }
        ],
        'general': [
            { texto: '¿Cómo calificarías tu experiencia general?', tipo: 'scale', required: true },
            { texto: '¿Qué es lo que más te gustó?', tipo: 'text', required: false },
            { texto: '¿Qué aspectos crees que deberíamos mejorar?', tipo: 'text', required: false },
            { texto: '¿Volverías a utilizar nuestros servicios?', tipo: 'single', opciones: ['Definitivamente sí', 'Probablemente sí', 'No estoy seguro', 'Probablemente no', 'Definitivamente no'], required: true }
        ]
    };

    function suggestQuestions() {
        // Abrir modal de selección
        const modal = new bootstrap.Modal(document.getElementById('suggestQuestionsModal'));
        modal.show();
    }

    // Event listeners para las opciones del modal
    document.addEventListener('click', function(e) {
        if (e.target.closest('.template-option')) {
            const btn = e.target.closest('.template-option');
            const templateKey = btn.dataset.template;
            const template = questionTemplates[templateKey];
            
            if (template) {
                // Cerrar modal
                const modal = bootstrap.Modal.getInstance(document.getElementById('suggestQuestionsModal'));
                if (modal) modal.hide();
                
                // Agregar preguntas
                template.forEach(q => {
                    addQuestionFromTemplate(q);
                });
                
                // Scroll al primer elemento agregado
                setTimeout(() => {
                    const firstQuestion = document.querySelector('.question-item');
                    if (firstQuestion) {
                        firstQuestion.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }, 500);
            }
        }
    });

    function addQuestionFromTemplate(templateData) {
        questionCount++;
        const container = document.getElementById('questions-list');
        const template = document.getElementById('questionTemplate');

        if (!container || !template) return;

        const clone = template.content.cloneNode(true);

        // Asignar datos del template
        clone.querySelector('.question-number').textContent = `Pregunta ${questionCount}`;
        clone.querySelector('.question-title').value = templateData.texto;
        clone.querySelector('.question-type').value = templateData.tipo;
        clone.querySelector('.question-required').checked = templateData.required || false;

        // Si tiene opciones, agregarlas
        if (templateData.opciones && ['single', 'multi'].includes(templateData.tipo)) {
            const optsContainer = clone.querySelector('.options-container');
            optsContainer.classList.remove('d-none');
            clone.querySelector('.question-options').value = templateData.opciones.join(', ');
        }

        // IDs únicos para el checkbox
        const uid = `req_${Date.now()}_${Math.random().toString(36).substr(2,5)}`;
        const check = clone.querySelector('.question-required');
        const label = clone.querySelector('.form-check-label');

        if (check) check.id = uid;
        if (label) label.setAttribute('for', uid);

        // Eventos internos de la tarjeta
        const typeSelect = clone.querySelector('.question-type');
        const optsDiv = clone.querySelector('.options-container');

        if(typeSelect) typeSelect.addEventListener('change', function() {
            if(['single', 'multi'].includes(this.value)) {
                optsDiv.classList.remove('d-none');
                setTimeout(() => optsDiv.querySelector('input').focus(), 100);
            } else {
                optsDiv.classList.add('d-none');
            }
        });

        // Botón Eliminar
        const btnClose = clone.querySelector('.btn-close');
        if(btnClose) btnClose.addEventListener('click', function() {
            this.closest('.question-item').remove();
        });

        container.appendChild(clone);
    }

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

            if (!title) return alert('Por favor, ingresa un título para tu encuesta.');
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

        if(typeSelect) typeSelect.addEventListener('change', function() {
            if(['single', 'multi'].includes(this.value)) {
                optsDiv.classList.remove('d-none');
                setTimeout(() => optsDiv.querySelector('input').focus(), 100);
            } else {
                optsDiv.classList.add('d-none');
            }
        });

        // Botón Eliminar
        const btnClose2 = clone.querySelector('.btn-close');
        if(btnClose2) btnClose2.addEventListener('click', function() {
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

        // Inyectar al resumen
        document.getElementById('review-title').innerText = title;
        document.getElementById('review-description').innerText = desc || 'Sin descripción';

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
            title: document.getElementById('surveyTitle').value.trim(),
            description: document.getElementById('surveyDescription').value.trim(),
            category: 'general',
            questions: []
        };

        document.querySelectorAll('.question-item').forEach(el => {
            const type = el.querySelector('.question-type').value;
            const qData = {
                text: el.querySelector('.question-title').value.trim(),
                type: type,
                required: el.querySelector('.question-required').checked
            };
            if (['single', 'multi'].includes(type)) {
                qData.options = el.querySelector('.question-options').value
                    .split(',')
                    .map(s => s.trim())
                    .filter(Boolean);
            }
            surveyData.questions.push(qData);
        });

        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        fetch('/surveys/create/', {
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