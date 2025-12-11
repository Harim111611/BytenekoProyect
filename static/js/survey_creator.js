document.addEventListener('DOMContentLoaded', function() {
    // --- CONSTANTES Y REFERENCIAS DOM GLOBALES ---
    const dom = {
        // Wizard Steps
        steps: [
            document.getElementById('card-step-1'),
            document.getElementById('card-step-2'),
            document.getElementById('card-step-3')
        ],
        contents: [
            document.getElementById('step-1-content'),
            document.getElementById('step-2-content'),
            document.getElementById('step-3-content')
        ],
        // Botones Wizard
        btnNext1: document.getElementById('btn-next-1'),
        btnPrev2: document.getElementById('btn-to-step-1-from-2'),
        btnNext2: document.getElementById('btn-next-2'),
        btnPrev3: document.getElementById('btn-to-step-2-from-3'),
        btnPublish: document.getElementById('btn-publish'), // Botón Publicar
        
        // Progress
        progressBar: document.getElementById('progressBar'),
        percentCounter: document.getElementById('percentCounter'),
        stepCounter: document.getElementById('stepCounter'),

        // Survey Form
        questionsList: document.getElementById('questions-list'),
        btnAddQuestion: document.getElementById('btn-add-custom-question'),
        btnSuggestQuestions: document.getElementById('btn-suggest-questions'),
        surveyTitle: document.getElementById('surveyTitle'),
        surveyDesc: document.getElementById('surveyDescription'),

        // Templates (Guardar)
        btnSaveTemplate: document.getElementById('btn-save-template'),
        saveTemplateModal: document.getElementById('saveTemplateModal'),
        btnConfirmSaveTemplate: document.getElementById('btn-confirm-save-template'),
        saveTemplateForm: document.getElementById('saveTemplateForm'),

        // Templates (CRUD y Listado)
        templateListContainer: document.getElementById('template-list-container'),
        crudTemplateModal: document.getElementById('crudTemplateModal'),
        suggestQuestionsModal: document.getElementById('suggestQuestionsModal'),

        // CSV Import & Bulk
        importForm: document.getElementById('importCsvForm'),
        bulkDeleteBtn: document.getElementById('bulkDeleteBtn'),
        csrfInput: document.querySelector('[name=csrfmiddlewaretoken]')
    };

    let currentStep = 1;
    // Este contador ahora se sincroniza SIEMPRE con la cantidad real de preguntas
    let questionCount = 0;
    let loadedCustomTemplates = []; 

    // --- HELPER: CSRF TOKEN ---
    const getCSRFToken = () => {
        if (dom.csrfInput && dom.csrfInput.value) return dom.csrfInput.value;
        
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, 10) === ('csrftoken=')) {
                    cookieValue = decodeURIComponent(cookie.substring(10));
                    break;
                }
            }
        }
        if (!cookieValue) {
             const meta = document.querySelector('meta[name="csrf-token"]');
             if (meta) return meta.content;
        }
        
        return cookieValue;
    };

    // --- HELPER: TOAST ---
    function showToast(msg, type = 'info') {
        let toastEl = document.getElementById('mainToast');
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.id = 'mainToast';
            document.body.appendChild(toastEl);
        }
        toastEl.className = `toast align-items-center text-bg-${type} border-0 position-fixed bottom-0 end-0 m-3`;
        toastEl.style.zIndex = 9999;
        toastEl.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${msg}</div>
                <button type="button" class="btn-close me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>`;
        
        const bsToast = bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 3000 });
        bsToast.show();
    }

    // =====================================================
    // 1. LÓGICA DEL WIZARD (PASOS)
    // =====================================================
    function updateWizardUI(step) {
        if (dom.contents && Array.isArray(dom.contents)) {
            dom.contents.forEach((el, i) => {
                if(el) el.classList.toggle('d-none', i + 1 !== step);
            });
        }
        
        if (dom.steps && Array.isArray(dom.steps)) {
            dom.steps.forEach((card, index) => {
                if(!card) return;
                card.classList.remove('active', 'completed');
                if (index + 1 < step) card.classList.add('completed');
                if (index + 1 === step) card.classList.add('active');
            });
        }
        
        const percent = step === 1 ? 33 : (step === 2 ? 66 : 100);
        if(dom.progressBar) dom.progressBar.style.width = `${percent}%`;
        if(dom.stepCounter) dom.stepCounter.innerText = `Paso ${step} de 3`;
        if(dom.percentCounter) dom.percentCounter.innerText = `${percent}% completado`;
        currentStep = step;
    }

    function validateStep(step) {
        if (step === 1) {
            if (!dom.surveyTitle.value.trim()) {
                showToast('Por favor, ingresa un título para tu encuesta.', 'warning');
                dom.surveyTitle.focus();
                return false;
            }
        }
        if (step === 2) {
            const items = dom.questionsList.querySelectorAll('.question-item');
            if (items.length === 0) {
                showToast('Agrega al menos una pregunta.', 'warning');
                return false;
            }
            let allValid = true;
            items.forEach(q => {
                const title = q.querySelector('.question-title').value.trim();
                if (!title) {
                    q.querySelector('.question-title').classList.add('is-invalid');
                    allValid = false;
                } else {
                    q.querySelector('.question-title').classList.remove('is-invalid');
                }
            });
            if (!allValid) {
                showToast('Completa los títulos de todas las preguntas.', 'warning');
                return false;
            }
            // Al validar el paso 2, renderizamos el preview actualizado
            renderPreview();
        }
        return true;
    }

    function goToStep(step) {
        if (step > currentStep) {
            if (!validateStep(currentStep)) return;
        }
        updateWizardUI(step);
    }

    if(dom.btnNext1) dom.btnNext1.addEventListener('click', () => goToStep(2));
    if(dom.btnPrev2) dom.btnPrev2.addEventListener('click', () => updateWizardUI(1));
    if(dom.btnNext2) dom.btnNext2.addEventListener('click', () => goToStep(3));
    if(dom.btnPrev3) dom.btnPrev3.addEventListener('click', () => updateWizardUI(2));


    // =====================================================
    // 2. GESTIÓN DE PREGUNTAS
    // =====================================================

    // Recalcula los textos "Pregunta X" y sincroniza questionCount
    function refreshQuestionNumbers() {
        if (!dom.questionsList) return;
        const items = dom.questionsList.querySelectorAll('.question-item');

        items.forEach((card, idx) => {
            const numberLabel = card.querySelector('.question-number');
            if (numberLabel) {
                numberLabel.textContent = `Pregunta ${idx + 1}`;
            }
        });

        // Mantener el contador global igual al número real de preguntas
        questionCount = items.length;
    }

    // Observador que renumera automáticamente cuando se agregan o eliminan tarjetas
    if (dom.questionsList && 'MutationObserver' in window) {
        const questionListObserver = new MutationObserver((mutations) => {
            let shouldRefresh = false;
            for (const mutation of mutations) {
                if (mutation.type === 'childList') {
                    shouldRefresh = true;
                    break;
                }
            }
            if (shouldRefresh) {
                refreshQuestionNumbers();
            }
        });

        questionListObserver.observe(dom.questionsList, {
            childList: true
        });
    }

    function createQuestionElement(data = null) {
        const template = document.getElementById('questionTemplate');
        if (!template || !dom.questionsList) return;

        const clone = template.content.cloneNode(true);
        const card = clone.querySelector('.question-item');

        const titleInput = card.querySelector('.question-title');
        const typeSelect = card.querySelector('.question-type');
        const reqCheck = card.querySelector('.question-required');
        const optsContainer = card.querySelector('.options-container');
        const optsInput = card.querySelector('.question-options');
        const numberLabel = card.querySelector('.question-number');

        const uniqueId = `req_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
        if(reqCheck) reqCheck.id = uniqueId;
        const labelCheck = card.querySelector('.form-check-label');
        if(labelCheck) labelCheck.setAttribute('for', uniqueId);

        if (numberLabel) {
            numberLabel.textContent = 'Pregunta'; // placeholder temporal
        }

        if (data) {
            titleInput.value = data.texto || data.text; // Soporte para 'text' o 'texto'
            // Usar 'dtype' si está presente (de backend CSV preview), si no, fallback a tipo/type
            typeSelect.value = data.dtype || data.tipo || data.type;
            if(reqCheck) reqCheck.checked = data.required || data.is_required || false;

            const currentType = data.dtype || data.tipo || data.type;
            const options = data.opciones || data.options;

            // CORRECCIÓN: Ahora incluimos 'select' para mostrar las opciones si viene cargado
            if (['single', 'multi', 'select'].includes(currentType) && options) {
                optsContainer.classList.remove('d-none');
                optsInput.value = Array.isArray(options) ? options.join(', ') : options;
            }
        }

        dom.questionsList.appendChild(clone);

        // Renumerar todas las tarjetas después de agregar
        refreshQuestionNumbers();
        
        if (!data) {
            setTimeout(() => {
                card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                titleInput.focus();
            }, 100);
        }
        toggleSaveTemplateBtn();
    }

    if (dom.questionsList) {
        dom.questionsList.addEventListener('click', function(e) {
            if (e.target.closest('.btn-close')) {
                const card = e.target.closest('.question-item');
                if (card) {
                    card.remove();
                    // Renumerar después de eliminar
                    refreshQuestionNumbers();
                    toggleSaveTemplateBtn();
                }
            }
        });

        // CORRECCIÓN: Detectar cambio a 'select' para mostrar campo de opciones
        dom.questionsList.addEventListener('change', function(e) {
            if (e.target.classList.contains('question-type')) {
                const select = e.target;
                const card = select.closest('.question-item');
                const optsDiv = card.querySelector('.options-container');
                
                // Si es single, multi o SELECT, mostramos el cuadro de opciones
                if (['single', 'multi', 'select'].includes(select.value)) {
                    optsDiv.classList.remove('d-none');
                    // Pequeño delay para enfocar si el usuario lo acaba de cambiar
                    setTimeout(() => {
                        const input = optsDiv.querySelector('input') || optsDiv.querySelector('textarea');
                        if(input) input.focus();
                    }, 50);
                } else {
                    optsDiv.classList.add('d-none');
                }
            }
        });
    }

    if(dom.btnAddQuestion) {
        dom.btnAddQuestion.addEventListener('click', () => createQuestionElement());
    }


    // =====================================================
    // 3. PLANTILLAS SUGERIDAS
    // =====================================================
    const questionTemplates = {
        'satisfaccion': [
            { texto: '¿Qué tan satisfecho estás con nuestro servicio?', tipo: 'scale', required: true },
            { texto: '¿Qué podríamos mejorar?', tipo: 'text', required: false },
            { texto: '¿Repetirías tu experiencia con nosotros?', tipo: 'scale', required: true },
            { texto: '¿Cómo calificarías la relación calidad-precio?', tipo: 'scale', required: true },
            { texto: '¿Qué aspecto te gustó más?', tipo: 'text', required: false }
        ],
        'nps': [
            { texto: '¿Qué probabilidad hay de que recomiendes nuestro producto/servicio a un amigo o colega?', tipo: 'scale', required: true },
            { texto: '¿Qué te motivó a darnos esa calificación?', tipo: 'text', required: false },
            { texto: '¿Qué podríamos hacer para mejorar tu puntuación?', tipo: 'text', required: false },
            { texto: '¿Has recomendado nuestro producto/servicio antes?', tipo: 'scale', required: false },
            { texto: '¿Qué característica valoras más?', tipo: 'text', required: false }
        ],
        'empleados': [
            { texto: '¿Te sientes valorado en tu trabajo?', tipo: 'scale', required: true },
            { texto: '¿Qué mejorarías en el ambiente laboral?', tipo: 'text', required: false },
            { texto: '¿Recomendarías esta empresa como lugar para trabajar?', tipo: 'scale', required: true },
            { texto: '¿Tienes oportunidades de desarrollo profesional?', tipo: 'scale', required: true },
            { texto: '¿Cómo calificarías la comunicación interna?', tipo: 'scale', required: false }
        ],
        'educacion': [
            { texto: '¿Cómo calificarías la calidad de la enseñanza?', tipo: 'scale', required: true },
            { texto: '¿Qué aspectos del curso te parecieron más útiles?', tipo: 'text', required: false },
            { texto: '¿Qué sugerencias tienes para mejorar el curso?', tipo: 'text', required: false },
            { texto: '¿El material proporcionado fue suficiente?', tipo: 'scale', required: false },
            { texto: '¿Recomendarías este curso a otros?', tipo: 'scale', required: true }
        ],
        'producto': [
            { texto: '¿El producto cumplió con tus expectativas?', tipo: 'scale', required: true },
            { texto: '¿Qué características te gustaron más?', tipo: 'text', required: false },
            { texto: '¿Qué mejorarías del producto?', tipo: 'text', required: false },
            { texto: '¿El producto fue fácil de usar?', tipo: 'scale', required: true },
            { texto: '¿Volverías a comprar este producto?', tipo: 'scale', required: true }
        ],
        'servicio': [
            { texto: '¿Cómo calificarías la atención recibida?', tipo: 'scale', required: true },
            { texto: '¿El personal resolvió tus dudas?', tipo: 'scale', required: true },
            { texto: '¿El tiempo de espera fue adecuado?', tipo: 'scale', required: false },
            { texto: '¿Qué sugerencias tienes para mejorar el servicio?', tipo: 'text', required: false },
            { texto: '¿Volverías a utilizar este servicio?', tipo: 'scale', required: true }
        ],
        'general': [
            { texto: 'Comentarios generales', tipo: 'text', required: false },
            { texto: 'Califica tu experiencia', tipo: 'scale', required: true },
            { texto: '¿Qué fue lo que más te gustó?', tipo: 'text', required: false },
            { texto: '¿Qué mejorarías en general?', tipo: 'text', required: false },
            { texto: '¿Recomendarías esta experiencia?', tipo: 'scale', required: true }
        ]
    };

    if(dom.btnSuggestQuestions) {
        dom.btnSuggestQuestions.addEventListener('click', () => {
            fetchTemplates(); 
            const modal = new bootstrap.Modal(dom.suggestQuestionsModal);
            modal.show();
        });
    }

    document.addEventListener('click', function(e) {
        
        const btnDeleteCustom = e.target.closest('.btn-delete-custom');
        if (btnDeleteCustom) {
            e.stopPropagation();
            const id = btnDeleteCustom.dataset.id;
            handleDeleteTemplate(id);
            return;
        }

        const btnPre = e.target.closest('.template-option');
        if (btnPre) {
            const key = btnPre.dataset.template;
            const templates = questionTemplates[key] || questionTemplates['general'];
            const modal = bootstrap.Modal.getInstance(dom.suggestQuestionsModal);
            if(modal) modal.hide();
            templates.forEach(t => createQuestionElement(t));
            showToast(`Se agregaron ${templates.length} preguntas sugeridas`, 'success');
            return;
        }

        const btnCustom = e.target.closest('.custom-template-option');
        if (btnCustom) {
            const id = btnCustom.dataset.id;
            const template = loadedCustomTemplates.find(t => t.id == id);

            if (template && template.structure) {
                const modal = bootstrap.Modal.getInstance(dom.suggestQuestionsModal);
                if(modal) modal.hide();

                let count = 0;
                template.structure.forEach(q => {
                    const mappedData = {
                        texto: q.text,
                        tipo: q.type,
                        required: q.required,
                        opciones: q.options
                    };
                    createQuestionElement(mappedData);
                    count++;
                });
                showToast(`Se importó la plantilla "${template.title}"`, 'success');
            } else {
                showToast('Error al cargar la plantilla', 'danger');
            }
        }
    });


    // =====================================================
    // 4. GUARDAR PLANTILLA
    // =====================================================
    function toggleSaveTemplateBtn() {
        if (!dom.btnSaveTemplate) return;
        const count = dom.questionsList ? dom.questionsList.querySelectorAll('.question-item').length : 0;
        dom.btnSaveTemplate.style.display = count > 0 ? 'inline-block' : 'none';
    }

    if(dom.btnSaveTemplate) {
        dom.btnSaveTemplate.addEventListener('click', () => {
            let emptyQuestion = false;
            dom.questionsList.querySelectorAll('.question-item').forEach(el => {
                const qTitle = el.querySelector('.question-title').value.trim();
                if (!qTitle) emptyQuestion = true;
            });
            if (emptyQuestion) {
                showToast('No puedes guardar la plantilla: hay preguntas sin texto.', 'warning');
                return;
            }
            if(dom.saveTemplateModal) {
                const modal = new bootstrap.Modal(dom.saveTemplateModal);
                dom.saveTemplateForm.reset();
                modal.show();
            }
        });
    }

    if(dom.btnConfirmSaveTemplate) {
        dom.btnConfirmSaveTemplate.addEventListener('click', async function() {
            const title = document.getElementById('templateName').value.trim();
            const description = document.getElementById('templateDesc').value.trim();
            const category = document.getElementById('templateCat').value.trim() || 'General';

            if(!title) return showToast('El nombre de la plantilla es obligatorio', 'warning');

            const structure = [];
            let emptyQuestion = false;
            dom.questionsList.querySelectorAll('.question-item').forEach((el, i) => {
                const qTitle = el.querySelector('.question-title').value.trim();
                if (!qTitle) emptyQuestion = true;
                const qType = el.querySelector('.question-type').value;
                const qReq = el.querySelector('.question-required').checked;
                let qOpts = [];
                // CORRECCIÓN: Guardar opciones también si es 'select'
                if(['single','multi', 'select'].includes(qType)){
                    qOpts = el.querySelector('.question-options').value.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean);
                }
                structure.push({ text: qTitle, type: qType, required: qReq, options: qOpts, order: i+1 });
            });

            if (structure.length === 0) {
                return showToast('No puedes guardar una plantilla vacía.', 'warning');
            }
            if (emptyQuestion) {
                return showToast('No puedes guardar la plantilla: hay preguntas sin texto.', 'warning');
            }

            const originalBtnText = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Guardando...';

            try {
                const token = getCSRFToken();
                if (!token) throw new Error('No CSRF token found');

                const resp = await fetch('/surveys/templates/create/', {
                    method: 'POST',
                    headers: { 'Content-Type':'application/json', 'X-CSRFToken': token },
                    body: JSON.stringify({title, description, category, structure})
                });
                const data = await resp.json();
                
                if(data.success) {
                    showToast('Plantilla guardada exitosamente', 'success');
                    
                    const modalEl = document.getElementById('saveTemplateModal');
                    const modalInstance = bootstrap.Modal.getInstance(modalEl);
                    if(modalInstance) modalInstance.hide();

                    setTimeout(() => {
                        document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                        document.body.classList.remove('modal-open');
                        document.body.style.overflow = 'auto';
                        document.body.style.paddingRight = '';
                    }, 300);

                    fetchTemplates(); 

                } else {
                    showToast(data.error || 'Error al guardar plantilla', 'danger');
                }
            } catch (err) {
                console.error(err);
                showToast('Error de conexión o permisos', 'danger');
            } finally {
                this.disabled = false;
                this.innerHTML = originalBtnText;
            }
        });
    }

    // =====================================================
    // 5. CRUD Y LISTADO DE PLANTILLAS
    // =====================================================
    async function fetchTemplates() {
        try {
            const resp = await fetch('/surveys/templates/list/');
            if(!resp.ok) throw new Error('Error fetching');
            const templates = await resp.json();
            
            loadedCustomTemplates = templates;

            renderTemplateList(templates); 
            renderSelectionModalTemplates(templates); 

        } catch(e) {
            console.error(e);
            if(dom.templateListContainer) dom.templateListContainer.innerHTML = '<div class="alert alert-danger">Error al cargar</div>';
        }
    }

    function renderSelectionModalTemplates(templates) {
        const container = document.getElementById('my-templates-container');
        const section = document.getElementById('my-custom-templates-section');
        
        if (!container || !section) return;

        container.innerHTML = ''; 

        if (templates.length > 0) {
            section.classList.remove('d-none');
            templates.forEach(t => {
                const col = document.createElement('div');
                col.className = 'col-md-6 animate__animated animate__fadeIn';
                col.innerHTML = `
                    <div class="position-relative h-100">
                        <button type="button" class="btn btn-outline-info w-100 text-start p-3 custom-template-option border-2 h-100" data-id="${t.id}">
                            <div class="d-flex align-items-start gap-3 pe-3">
                                <div class="bg-info-subtle text-info rounded-circle p-2 d-flex align-items-center justify-content-center" style="width: 48px; height: 48px; flex-shrink: 0;">
                                    <i class="bi bi-person-fill-gear fs-4"></i>
                                </div>
                                <div class="overflow-hidden">
                                    <div class="fw-bold text-truncate">${t.title}</div>
                                    <small class="text-muted d-block text-truncate">${t.description || 'Sin descripción'}</small>
                                    <span class="badge bg-secondary-subtle text-secondary-emphasis mt-1" style="font-size: 0.7rem;">${t.structure ? t.structure.length : '0'} preguntas</span>
                                </div>
                            </div>
                        </button>
                        <button type="button" class="btn btn-sm btn-danger position-absolute top-0 end-0 m-2 rounded-circle shadow-sm btn-delete-custom d-flex align-items-center justify-content-center"
                                data-id="${t.id}" style="width: 26px; height: 26px; padding: 0; z-index: 10;" title="Eliminar plantilla">
                            <i class="bi bi-x-lg" style="font-size: 0.8rem;"></i>
                        </button>
                    </div>
                `;
                container.appendChild(col);
            });
        } else {
            section.classList.add('d-none');
        }
    }

    function renderTemplateList(templates) {
        if(!dom.templateListContainer) return;
        dom.templateListContainer.innerHTML = '';
        if(!templates.length) {
            dom.templateListContainer.innerHTML = '<div class="alert alert-info">No hay plantillas guardadas.</div>';
            return;
        }
        templates.forEach(t => {
            const div = document.createElement('div');
            div.className = 'card mb-2 shadow-sm';
            div.innerHTML = `
                <div class="card-body d-flex justify-content-between align-items-center py-2">
                    <div>
                        <strong>${t.title}</strong> <span class="badge bg-secondary ms-1">${t.category}</span>
                        <div class="small text-muted text-truncate" style="max-width: 250px;">${t.description || 'Sin descripción'}</div>
                    </div>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-danger" data-delete="${t.id}" title="Eliminar"><i class="bi bi-trash"></i></button>
                    </div>
                </div>`;
            dom.templateListContainer.appendChild(div);
        });
    }

    // --- ELIMINACIÓN DE PLANTILLAS ---
    let templateToDeleteId = null;
    const deleteTemplateModal = document.getElementById('deleteTemplateModal');
    const btnConfirmDeleteTemplate = document.getElementById('btn-confirm-delete-template');

    async function handleDeleteTemplate(id) {
        templateToDeleteId = id;
        if(deleteTemplateModal) {
            const modal = new bootstrap.Modal(deleteTemplateModal);
            modal.show();
        } else {
            if(confirm('¿Eliminar esta plantilla?')) {
                performDelete(id);
            }
        }
    }

    async function performDelete(id) {
        const url = `/surveys/templates/${id}/delete/`;
        const token = getCSRFToken();
        const headers = { 
            'X-CSRFToken': token,
            'X-Requested-With': 'XMLHttpRequest' 
        };
        
        if (!token) {
             showToast('Error de seguridad: No se encontró el token CSRF.', 'danger');
             return false; 
        }

        try {
            let resp = await fetch(url, { method: 'DELETE', headers: headers });
            
            if (resp.status === 403 || resp.status === 405) { 
                console.warn('DELETE falló, reintentando con POST.');
                resp = await fetch(url, { method: 'POST', headers: headers });
            }

            const data = await resp.json();

            if(data.success) {
                showToast('Plantilla eliminada', 'success');
                return true;
            } else {
                showToast('Error al eliminar: ' + (data.error || 'Respuesta inesperada'), 'danger');
                return false;
            }
        } catch(err) {
            console.error('Error de red/servidor al eliminar:', err);
            showToast('Error de red/servidor', 'danger');
            return false;
        }
    }

    if(btnConfirmDeleteTemplate) {
        btnConfirmDeleteTemplate.addEventListener('click', async function() {
            if(!templateToDeleteId) return;
            
            const originalText = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Eliminando...';
            
            const success = await performDelete(templateToDeleteId);
            
            this.disabled = false;
            this.innerHTML = originalText;
            templateToDeleteId = null;

            const modalInstance = bootstrap.Modal.getInstance(deleteTemplateModal);
            if (modalInstance) {
                 modalInstance.hide();
            } else {
                 document.querySelectorAll('.modal-backdrop').forEach(el => el.remove());
                 document.body.classList.remove('modal-open');
                 document.body.style.overflow = 'auto';
            }

            if(success) {
                fetchTemplates();
            }
        });
    }

    if(dom.templateListContainer) {
        dom.templateListContainer.addEventListener('click', function(e) {
            const btnDelete = e.target.closest('[data-delete]');
            if(btnDelete) {
                const id = btnDelete.dataset.delete;
                handleDeleteTemplate(id);
            }
        });
    }


    // =====================================================
    // 6. LÓGICA DE PUBLICACIÓN (PUBLISH)
    // =====================================================
    if(dom.btnPublish) {
        dom.btnPublish.addEventListener('click', async function() {
            // 1. Validar si el paso 2 (preguntas) es válido
            if (!validateStep(2)) {
                // Si la validación falla, nos aseguramos de que el usuario regrese a ese paso
                goToStep(2); 
                return;
            }

            // 2. Recolectar todos los datos (título, descripción, y la estructura de preguntas)
            const title = dom.surveyTitle.value.trim();
            const description = dom.surveyDesc.value.trim();

            const structure = [];
            dom.questionsList.querySelectorAll('.question-item').forEach((el, i) => {
                const qTitle = el.querySelector('.question-title').value.trim();
                const qType = el.querySelector('.question-type').value;
                const qReq = el.querySelector('.question-required').checked;
                let qOpts = [];
                if(['single','multi', 'select'].includes(qType)){
                    qOpts = el.querySelector('.question-options').value.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean);
                }
                structure.push({ text: qTitle, type: qType, required: qReq, options: qOpts, order: i+1 });
            });
            
            const payload = {
                title: title,
                description: description,
                structure: structure, 
                status: 'active' 
            };

            const originalBtnText = this.innerHTML;
            this.disabled = true;
            this.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Publicando...';

            try {
                const token = getCSRFToken();
                if (!token) throw new Error('No CSRF token found');

                const publishUrl = '/surveys/create_survey/'; 
                
                const resp = await fetch(publishUrl, {
                    method: 'POST',
                    headers: { 'Content-Type':'application/json', 'X-CSRFToken': token },
                    body: JSON.stringify(payload)
                });
                
                const data = await resp.json();
                
                if(data.success) {
                    showToast('¡Encuesta publicada exitosamente!', 'success');
                    window.location.href = data.redirect_url || '/surveys/list/'; 
                } else {
                    showToast(data.error || 'Error al publicar la encuesta.', 'danger');
                }

            } catch (err) {
                console.error('Error de red al publicar:', err);
                showToast('Error de conexión o permisos al intentar publicar.', 'danger');
            } finally {
                this.disabled = false;
                this.innerHTML = originalBtnText;
            }
        });
    }


    // =====================================================
    // 7. PREVIEW RENDER (CORREGIDO Y MEJORADO)
    // =====================================================
    function renderPreview() {
        const title = dom.surveyTitle.value || 'Sin título';
        const desc = dom.surveyDesc.value || 'Sin descripción';

        // Detectar modo noche
        const isDarkMode = document.body.classList.contains('dark-mode') || window.matchMedia('(prefers-color-scheme: dark)').matches;

        // Colores para modo noche
        const darkBg = 'background-color: #23272b;';
        const darkBorder = 'border: 1px solid #444;';
        const darkText = 'color: #e0e0e0;';
        const darkMuted = 'color: #b0b0b0;';
        const darkCard = 'background-color: #181a1b; border: 1px solid #333;';

        // Actualizar textos del header del preview
        ['review-title', 'preview-header-title'].forEach(id => {
            const el = document.getElementById(id); if(el) el.innerText = title;
        });
        ['review-description', 'preview-header-desc'].forEach(id => {
             const el = document.getElementById(id); if(el) el.innerText = desc;
        });

        const container = document.getElementById('preview-container');
        if(!container) return;

        container.innerHTML = '';
        const items = dom.questionsList.querySelectorAll('.question-item');

        const countBadge = document.getElementById('review-count');
        if(countBadge) countBadge.innerText = items.length;

        items.forEach((q, idx) => {
            const qTitle = q.querySelector('.question-title').value;
            const qType = q.querySelector('.question-type').value;
            const qReq = q.querySelector('.question-required').checked;

            const card = document.createElement('div');
            card.className = 'card mb-3 border-0 shadow-sm';
            if (isDarkMode) card.style = darkCard;

            let inputHTML = '';
            // Estilos inline para consistencia en el preview
            const bgStyle = isDarkMode ? darkBg : 'background-color: var(--bs-body-tertiary);';
            const borderStyle = isDarkMode ? darkBorder : 'border: 1px solid var(--bs-border-color);';
            const textStyle = isDarkMode ? darkText : '';
            const mutedStyle = isDarkMode ? darkMuted : 'color: var(--bs-secondary-color);';

            if(qType === 'text') {
                inputHTML = `<textarea class="form-control" rows="2" disabled style="${bgStyle} ${borderStyle} ${textStyle}"></textarea>`;
            } else if (qType === 'number') {
                inputHTML = `<input type="number" class="form-control" disabled placeholder="123" style="${bgStyle} ${borderStyle} ${textStyle}">`;
            } else if (qType === 'scale') {
                // Escala 0-10 mejorada (NPS style)
                const scaleNums = [0,1,2,3,4,5,6,7,8,9,10];
                inputHTML = `
                    <div class="d-flex justify-content-between gap-1 mt-2 overflow-auto pb-2">
                        ${scaleNums.map(n => `
                            <div class="d-flex align-items-center justify-content-center border rounded flex-fill p-2" 
                                 style="min-width: 35px; height: 35px; ${bgStyle} ${borderStyle} ${mutedStyle} font-weight: 500;">
                                ${n}
                            </div>
                        `).join('')}
                    </div>
                    <div class="d-flex justify-content-between small px-1" style="${mutedStyle}">
                        <span>Nada probable</span>
                        <span>Muy probable</span>
                    </div>`;
            } else if (['single', 'multi', 'select'].includes(qType)) {
                const rawOpts = q.querySelector('.question-options').value;
                const opts = rawOpts.split(/[\n,]+/).map(s=>s.trim()).filter(Boolean);
                if (opts.length === 0) {
                    inputHTML = `<div class="fst-italic small p-2 border border-dashed rounded text-center" style="${bgStyle} ${borderStyle} ${mutedStyle}">Sin opciones definidas</div>`;
                } else {
                    if (qType === 'select') {
                        inputHTML = `
                            <select class="form-select" disabled style="${bgStyle} ${borderStyle} ${textStyle}">
                                <option selected>Selecciona una opción...</option>
                                ${opts.map(opt => `<option>${opt}</option>`).join('')}
                            </select>`;
                    } else {
                        const inputType = qType === 'single' ? 'radio' : 'checkbox';
                        // Forzar fondo y borde en modo noche
                        const checkBg = isDarkMode ? 'background-color:#23272b !important;border-color:#666 !important;' : '';
                        inputHTML = `<div class="d-flex flex-column gap-2">` + 
                            opts.map((opt, i) => {
                                const darkClass = isDarkMode ? 'dark-preview' : '';
                                return `<div class="form-check p-2 border rounded" style="${bgStyle} ${borderStyle}">
                                    <input class="form-check-input ms-1 ${darkClass}" type="${inputType}" disabled style="${bgStyle} ${borderStyle} ${checkBg}">
                                    <label class="form-check-label w-100 ps-2" style="${textStyle}">${opt}</label>
                                </div>`;
                            }).join('') + 
                        `</div>`;
                    }
                }
            }

            card.innerHTML = `
                <div class="card-body p-4">
                    <h6 class="card-title fw-bold mb-3" style="${textStyle}">
                        ${idx + 1}. ${qTitle} 
                        ${qReq ? '<span class="text-danger" title="Obligatorio">*</span>' : ''}
                    </h6>
                    ${inputHTML}
                </div>`;

            container.appendChild(card);
        });
    }

    // Inicialización al cargar
    updateWizardUI(1);
    toggleSaveTemplateBtn();
    // En caso de que vengan preguntas desde el backend, renumeramos desde inicio
    refreshQuestionNumbers();
});