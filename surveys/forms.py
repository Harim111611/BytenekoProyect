
from django import forms
from .models import Encuesta, Pregunta, OpcionRespuesta

class DynamicRespuestaForm(forms.Form):
    def __init__(self, encuesta: Encuesta, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for p in encuesta.preguntas.all():
            field_name = f"q_{p.id}"
            if p.tipo == 'text':
                self.fields[field_name] = forms.CharField(
                    label=p.texto, required=p.es_obligatoria,
                    widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
                )
            elif p.tipo == 'multiple-choice':
                choices = [(o.id, o.texto) for o in p.opciones.all()]
                self.fields[field_name] = forms.ChoiceField(
                    label=p.texto, required=p.es_obligatoria,
                    choices=choices, widget=forms.Select(attrs={'class': 'form-select'})
                )
            elif p.tipo == 'satisfaction':
                self.fields[field_name] = forms.IntegerField(
                    label=p.texto, required=p.es_obligatoria,
                    min_value=1, max_value=10,
                    widget=forms.NumberInput(attrs={'class': 'form-control'})
                )
            elif p.tipo == 'nps':
                self.fields[field_name] = forms.IntegerField(
                    label=p.texto, required=p.es_obligatoria,
                    min_value=0, max_value=10,
                    widget=forms.NumberInput(attrs={'class': 'form-control'})
                )
