# surveys/forms.py
from django import forms
from .models import Survey, Question, AnswerOption

class SurveyForm(forms.ModelForm):
    """Formulario para crear/editar la configuración base de la encuesta."""
    class Meta:
        model = Survey
        fields = ['title', 'description', 'category', 'sample_goal', 'status']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Encuesta de Satisfacción 2025'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'category': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'sample_goal': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }
        help_texts = {
            'sample_goal': 'Define una meta de respuestas. Deja 0 para ilimitado.',
            'status': 'El estado inicial de la encuesta.'
        }

class DynamicRespuestaForm(forms.Form):
    def __init__(self, survey, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Usamos 'survey' en lugar de 'encuesta' para consistencia con el modelo
        for p in survey.questions.all():
            field_name = f"q_{p.id}"
            if p.type == 'text':
                self.fields[field_name] = forms.CharField(
                    label=p.text, required=p.is_required,
                    widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
                )
            elif p.type in ['single', 'multi']: # single o multiple-choice
                choices = [(o.id, o.text) for o in p.options.all()]
                widget = forms.Select(attrs={'class': 'form-select'})
                if p.type == 'multi':
                    widget = forms.SelectMultiple(attrs={'class': 'form-select'})
                
                self.fields[field_name] = forms.ChoiceField(
                    label=p.text, required=p.is_required,
                    choices=choices, widget=widget
                )
            elif p.type in ['scale', 'satisfaction']:
                self.fields[field_name] = forms.IntegerField(
                    label=p.text, required=p.is_required,
                    min_value=1, max_value=10,
                    widget=forms.NumberInput(attrs={'class': 'form-control'})
                )
            elif p.type in ['number', 'nps']:
                self.fields[field_name] = forms.IntegerField(
                    label=p.text, required=p.is_required,
                    min_value=0, max_value=10,
                    widget=forms.NumberInput(attrs={'class': 'form-control'})
                )