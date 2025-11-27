
from django import forms
from .models import Survey, Question, AnswerOption

class DynamicRespuestaForm(forms.Form):
    def __init__(self, encuesta: Encuesta, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for p in encuesta.questions.all():
            field_name = f"q_{p.id}"
            if p.type == 'text':
                self.fields[field_name] = forms.CharField(
                    label=p.text, required=p.is_required,
                    widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
                )
            elif p.type == 'multiple-choice':
                choices = [(o.id, o.text) for o in p.options.all()]
                self.fields[field_name] = forms.ChoiceField(
                    label=p.text, required=p.is_required,
                    choices=choices, widget=forms.Select(attrs={'class': 'form-select'})
                )
            elif p.type == 'satisfaction':
                self.fields[field_name] = forms.IntegerField(
                    label=p.text, required=p.is_required,
                    min_value=1, max_value=10,
                    widget=forms.NumberInput(attrs={'class': 'form-control'})
                )
            elif p.type == 'nps':
                self.fields[field_name] = forms.IntegerField(
                    label=p.text, required=p.is_required,
                    min_value=0, max_value=10,
                    widget=forms.NumberInput(attrs={'class': 'form-control'})
                )
