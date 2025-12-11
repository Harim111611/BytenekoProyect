"""surveys/forms.py"""
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import Survey, Question, AnswerOption

class SurveyForm(forms.ModelForm):
    """
    Formulario para crear/editar metadatos de la encuesta.
    """
    class Meta:
        model = Survey
        fields = ['title', 'description', 'category', 'sample_goal']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': _('Ej: Encuesta de Satisfacción 2024')
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': _('Describe el propósito de esta encuesta...')
            }),
            'category': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': _('General, RRHH, Marketing...')
            }),
            'sample_goal': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 0,
                'placeholder': '0 para sin límite'
            }),
        }
        labels = {
            'title': _('Título de la Encuesta'),
            'description': _('Descripción'),
            'category': _('Categoría'),
            'sample_goal': _('Meta de Respuestas (Opcional)'),
        }

class SurveyStructureForm(forms.Form):
    """
    Formulario para manejar la estructura JSON (Preguntas).
    No se vincula directamente a un modelo para permitir manipulación compleja antes de guardar.
    """
    structure_json = forms.JSONField(
        widget=forms.HiddenInput, 
        required=False,
        error_messages={'invalid': _("El formato de las preguntas no es válido.")}
    )

    def clean_structure_json(self):
        data = self.cleaned_data.get('structure_json')
        
        # Si es None o vacío, retornamos lista vacía (sin errores, puede ser borrador)
        if not data:
            return []
        
        if not isinstance(data, list):
            raise ValidationError(_("La estructura debe ser una lista de preguntas."))
        
        valid_types = [c[0] for c in Question.QuestionType.choices]
        
        for idx, q in enumerate(data):
            # Validar campos mínimos
            if not isinstance(q, dict):
                 raise ValidationError(_(f"El elemento #{idx+1} no es un objeto válido."))
                 
            if 'text' not in q or not str(q.get('text', '')).strip():
                raise ValidationError(_(f"La pregunta #{idx+1} no tiene texto."))
            
            if 'type' not in q or q['type'] not in valid_types:
                raise ValidationError(_(f"La pregunta #{idx+1} tiene un tipo inválido ({q.get('type')})."))
            
            # Validaciones específicas por tipo
            if q['type'] in ['single', 'multi']:
                options = q.get('options', [])
                if not isinstance(options, list) or len(options) < 2:
                    raise ValidationError(_(f"La pregunta '{q['text']}' requiere al menos 2 opciones."))
                
                # Validar que las opciones no estén vacías
                if any(not str(opt).strip() for opt in options):
                     raise ValidationError(_(f"La pregunta '{q['text']}' tiene opciones vacías."))

        return data

    def save_questions(self, survey):
        """
        Método helper para procesar el JSON validado y crear los objetos en BD.
        Realiza una operación atómica de reemplazo (Full Replacement).
        """
        questions_data = self.cleaned_data.get('structure_json')
        if questions_data is None:
            return

        # Limpiamos preguntas anteriores
        survey.questions.all().delete()
        
        if not questions_data:
            return

        # Creamos nuevas preguntas
        for i, q_data in enumerate(questions_data):
            question = Question.objects.create(
                survey=survey,
                text=q_data.get('text'),
                type=q_data.get('type'),
                order=i + 1,
                is_required=q_data.get('required', False),
                # Mapeamos campos adicionales si existen en el JSON y Modelo
                is_demographic=q_data.get('is_demographic', False)
            )
            
            # Creamos opciones si aplica
            options = q_data.get('options', [])
            if options and q_data['type'] in ['single', 'multi']:
                AnswerOption.objects.bulk_create([
                    AnswerOption(question=question, text=opt_text, order=j)
                    for j, opt_text in enumerate(options)
                    if str(opt_text).strip()
                ])