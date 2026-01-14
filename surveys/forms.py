from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Survey, Question, AnswerOption

class SurveyForm(forms.ModelForm):
    """
    Formulario base para metadatos de la encuesta.
    """
    class Meta:
        model = Survey
        fields = ['title', 'description', 'category', 'sample_goal']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('Ej: Encuesta de Satisfacción 2025')
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': _('Describe el propósito de esta encuesta...')
            }),
            'category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('General, RRHH, Marketing...')
            }),
            'sample_goal': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': '0 para ilimitado'
            }),
        }
        labels = {
            'title': _('Título de la Encuesta'),
            'description': _('Descripción'),
            'category': _('Categoría'),
            'sample_goal': _('Meta de Respuestas (Opcional)'),
        }

class SurveyUpdateForm(SurveyForm):
    """
    Formulario específico para EDICIÓN.
    """
    class Meta(SurveyForm.Meta):
        fields = ['title', 'description', 'category', 'status', 'sample_goal']
        widgets = SurveyForm.Meta.widgets.copy()
        widgets['status'] = forms.Select(attrs={'class': 'form-select'})

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            allowed = sorted(self.instance.get_allowed_status_transitions())
            self.fields['status'].widget.attrs['data-allowed-statuses'] = ','.join(allowed)
            self.fields['status'].widget.attrs['data-current-status'] = self.instance.status

        if self.instance and self.instance.is_imported:
            self.fields['status'].disabled = True
            self.fields['status'].help_text = _("El estado no se puede cambiar en encuestas importadas.")

        if self.instance and self.instance.status == Survey.STATUS_CLOSED:
            # Si está cerrada, se bloquean todos los parámetros salvo el título.
            for name, field in self.fields.items():
                if name == 'title':
                    continue
                field.disabled = True
                # Mensaje explícito para UI (si el template renderiza help_text)
                field.help_text = field.help_text or _("Bloqueado porque la encuesta está cerrada.")
            if 'status' in self.fields:
                self.fields['status'].help_text = _("La encuesta está cerrada. El estado es definitivo.")

    def clean(self):
        cleaned = super().clean()

        # Refuerzo backend: en encuestas cerradas solo se permite cambiar el título.
        if self.instance and self.instance.pk and self.instance.status == Survey.STATUS_CLOSED:
            for field_name in list(cleaned.keys()):
                if field_name == 'title':
                    continue
                # Revertir cualquier intento de modificación.
                if hasattr(self.instance, field_name):
                    cleaned[field_name] = getattr(self.instance, field_name)

        return cleaned

    def clean_status(self):
        new_status = self.cleaned_data.get('status')
        current_status = self.instance.status

        if not new_status or new_status == current_status:
            return new_status

        try:
            self.instance.validate_status_transition(new_status, from_status=current_status)
        except ValidationError as e:
            # Extract error message properly from ValidationError
            if hasattr(e, 'messages'):
                error_msg = ' '.join(e.messages)
            elif hasattr(e, 'message'):
                error_msg = e.message
            else:
                error_msg = str(e)
            raise forms.ValidationError(error_msg) from e

        return new_status

class SurveyStructureForm(forms.Form):
    """
    Formulario para manejar la estructura JSON (Preguntas).
    """
    structure_json = forms.JSONField(
        widget=forms.HiddenInput, 
        required=False,
        error_messages={'invalid': _("El formato de las preguntas no es válido.")}
    )

    def clean_structure_json(self):
        data = self.cleaned_data.get('structure_json')
        
        if not data:
            return []
        
        if not isinstance(data, list):
            raise ValidationError(_("La estructura debe ser una lista de preguntas."))
        
        valid_types = [c[0] for c in Question.TYPE_CHOICES]
        
        for idx, q in enumerate(data):
            if not isinstance(q, dict):
                 raise ValidationError(_(f"El elemento #{idx+1} no es un objeto válido."))
                 
            if 'text' not in q or not str(q.get('text', '')).strip():
                raise ValidationError(_(f"La pregunta #{idx+1} no tiene texto."))
            
            if 'type' not in q or q['type'] not in valid_types:
                raise ValidationError(_(f"La pregunta #{idx+1} tiene un tipo inválido ({q.get('type')})."))
            
            if q['type'] in ['single', 'multi']:
                options = q.get('options', [])
                if not isinstance(options, list) or len(options) < 2:
                    raise ValidationError(_(f"La pregunta '{q['text']}' requiere al menos 2 opciones."))
                
                if any(not str(opt).strip() for opt in options):
                     raise ValidationError(_(f"La pregunta '{q['text']}' tiene opciones vacías."))

        return data

    def save_questions(self, survey):
        questions_data = self.cleaned_data.get('structure_json')
        if questions_data is None:
            return

        survey.questions.all().delete()
        
        if not questions_data:
            return

        for i, q_data in enumerate(questions_data):
            question = Question.objects.create(
                survey=survey,
                text=q_data.get('text'),
                type=q_data.get('type'),
                order=i + 1,
                is_required=q_data.get('required', False),
                is_demographic=q_data.get('is_demographic', False)
            )
            
            options = q_data.get('options', [])
            if options and q_data['type'] in ['single', 'multi']:
                AnswerOption.objects.bulk_create([
                    AnswerOption(question=question, text=opt_text, order=j)
                    for j, opt_text in enumerate(options)
                    if str(opt_text).strip()
                ])