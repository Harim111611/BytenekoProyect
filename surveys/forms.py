# surveys/forms.py
from django import forms


# -----------------------------
# Formulario del PASO 1 (básico)
# -----------------------------
CATEGORY_CHOICES = [
    ("", "Selecciona el tipo de estudio"),
    ("satisfaction", "Satisfacción del cliente"),
    ("product", "Investigación de producto"),
    ("awareness", "Brand awareness"),
    ("concept", "Test de concepto"),
]


class SurveyBasicForm(forms.Form):
    name = forms.CharField(
        label="Nombre de la encuesta",
        max_length=180,
        widget=forms.TextInput(attrs={
            "class": "form-control form-control-lg rounded-3",
            "placeholder": "Ej. Satisfacción de clientes Q1 2024",
            "autocomplete": "off",
        }),
    )
    category = forms.ChoiceField(
        label="Categoría",
        choices=CATEGORY_CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select form-select-lg rounded-end-3",
        }),
    )
    description = forms.CharField(
        label="Descripción (opcional)",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control rounded-3",
            "rows": 5,
            "placeholder": "Describe brevemente el objetivo y qué información esperas obtener…",
        }),
    )


# -----------------------------
# Soporte para tipos de pregunta
# -----------------------------
class QuestionType:
    TEXT = "text"        # Texto libre
    SINGLE = "single"    # Opción única
    MULTI = "multi"      # Opción múltiple
    BOOLEAN = "boolean"  # Sí/No
    SCALE = "scale"      # Escala (1–5 por defecto)
    NUMBER = "number"    # Numérica
    DATE = "date"        # Fecha

    CHOICES = [
        (TEXT, "Texto libre"),
        (SINGLE, "Opción única"),
        (MULTI, "Opción múltiple"),
        (BOOLEAN, "Sí / No"),
        (SCALE, "Escala (1–5)"),
        (NUMBER, "Número"),
        (DATE, "Fecha"),
    ]


# -----------------------------
# Formulario del PASO 2 (pregunta)
# -----------------------------
class QuestionForm(forms.Form):
    qtype = forms.ChoiceField(
        label="Tipo",
        choices=QuestionType.CHOICES,
        widget=forms.Select(attrs={
            "class": "form-select",
        }),
    )
    text = forms.CharField(
        label="Pregunta",
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Escribe tu pregunta aquí…",
        }),
    )
    required = forms.BooleanField(
        label="Respuesta obligatoria",
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        }),
    )
    # Para tipos con opciones (single/multi). Una por línea.
    options = forms.CharField(
        label="Opciones (una por línea)",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Ej.\nMuy malo\nMalo\nRegular\nBueno\nExcelente",
        }),
    )

    def clean(self):
        data = super().clean()
        qtype = data.get("qtype")
        options_raw = (data.get("options") or "").strip()

        # Para SINGLE / MULTI se requieren al menos 2 opciones
        if qtype in (QuestionType.SINGLE, QuestionType.MULTI):
            opts = [o.strip() for o in options_raw.splitlines() if o.strip()]
            if len(opts) < 2:
                raise forms.ValidationError("Agrega al menos 2 opciones.")
            data["options_list"] = opts
        else:
            data["options_list"] = []

        # Para escala: si no mandan opciones, usar 1..5 por defecto
        if qtype == QuestionType.SCALE:
            if options_raw:
                opts = [o.strip() for o in options_raw.splitlines() if o.strip()]
                data["options_list"] = opts
            else:
                data["options_list"] = ["1", "2", "3", "4", "5"]

        return data
