from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
# surveys/views.py (arriba, junto con los otros imports)
from .forms import CATEGORY_CHOICES as CATEGORIES

# -----------------------------
# Catálogo simple de categorías
# -----------------------------
CATEGORY_CHOICES = [
    ("product", "Investigación de producto"),
    ("brand",   "Brand awareness"),
    ("ux",      "Experiencia de usuario"),
]

# Plantillas sugeridas por categoría
QUESTION_TEMPLATES = {
    "product": [
        {"text": "¿Con qué frecuencia utilizas este producto?", "qtype": "single_choice",
         "options": ["Diariamente", "Semanalmente", "Mensualmente", "Rara vez"]},
        {"text": "¿Qué características valoras más del producto?", "qtype": "open_text", "options": []},
        {"text": "¿El producto cumple con tus expectativas?", "qtype": "single_choice",
         "options": ["Sí", "No", "Parcialmente"]},
        {"text": "¿Qué precio estarías dispuesto a pagar?", "qtype": "open_text", "options": []},
        {"text": "¿Qué alternativas has considerado?", "qtype": "open_text", "options": []},
    ],
    "brand": [
        {"text": "¿Qué tan familiarizado estás con esta marca?", "qtype": "rating", "options": []},
        {"text": "¿Qué palabras asocias con esta marca?", "qtype": "open_text", "options": []},
        {"text": "¿Qué tan probable es que recomiendes la marca?", "qtype": "rating", "options": []},
    ],
    "ux": [
        {"text": "¿Qué tan fácil fue usar el producto/servicio?", "qtype": "rating", "options": []},
        {"text": "¿Qué mejorarías en la experiencia de uso?", "qtype": "open_text", "options": []},
        {"text": "¿Encontraste algún bloqueo o fricción?", "qtype": "open_text", "options": []},
    ],
}


# ==========================
# Paso 1: Información básica
# ==========================
@method_decorator(login_required, name="dispatch")
class CreateStep1View(View):
    template_name = "surveys/create_step_1.html"

    def get(self, request):
        data = request.session.get("survey_basic", {}) or {}
        ctx = {
            "form": {
                "name": data.get("name", ""),
                "category": data.get("category", ""),
                "description": data.get("description", ""),
            },
            "categories": CATEGORIES,
            "progress": 33,
            # can_continue sirve para dibujar el estado inicial (si hay datos en sesión)
            "can_continue": bool(data.get("name") and data.get("category")),
            # show_success solo si viene ?ok=1 (para no mostrar la franja verde en el primer GET vacío)
            "show_success": request.GET.get("ok") == "1",
        }
        return render(request, self.template_name, ctx)

    def post(self, request):
        name = (request.POST.get("name") or "").strip()
        category = (request.POST.get("category") or "").strip()
        description = (request.POST.get("description") or "").strip()

        # Si faltan los obligatorios, re-render con errores
        if not name or not category:
            ctx = {
                "form": {"name": name, "category": category, "description": description},
                "categories": CATEGORIES,
                "progress": 33,
                "can_continue": False,
                "show_success": False,
                "error_name": not bool(name),
                "error_category": not bool(category),
            }
            return render(request, self.template_name, ctx)

        # Guardar borrador en sesión
        request.session["survey_basic"] = {
            "name": name,
            "category": category,
            "description": description,
        }
        request.session.modified = True

        # Único CTA es continuar; si todo está ok, pasamos a Step 2
        # surveys/views.py  (dentro de CreateStep1View.post)
        return redirect("surveys:create_step_2")


# ==========================
# Paso 2: Construir preguntas
# ==========================
@method_decorator(login_required, name="dispatch")
class CreateStep2View(View):
    template_name = "surveys/create_step_2.html"
    http_method_names = ["get", "post", "head", "options"]

    def _base_ctx(self, request):
        basic = request.session.get("survey_basic")
        if not basic:
            return None

        category = basic.get("category") or "product"
        return {
            "step": 2,
            "progress": 67,
            "basic": basic,
            "recommended": QUESTION_TEMPLATES.get(category, QUESTION_TEMPLATES["product"]),
            "questions": request.session.get("survey_questions", []),
        }

    def get(self, request):
        ctx = self._base_ctx(request)
        if ctx is None:
            messages.info(request, "Primero completa la información básica.")
            return redirect("surveys:create_step_1")
        return render(request, self.template_name, ctx)

    def post(self, request):
        ctx = self._base_ctx(request)
        if ctx is None:
            messages.info(request, "Primero completa la información básica.")
            return redirect("surveys:create_step_1")

        action = (request.POST.get("action") or "").strip()
        questions = ctx["questions"]

        if action in {"add", "add_recommended"}:
            text = (request.POST.get("text") or "").strip()
            qtype = (request.POST.get("qtype") or "single_choice").strip()
            required = request.POST.get("required") in {"on", "true", "1"}
            options = [o.strip() for o in (request.POST.get("options") or "").splitlines() if o.strip()]
            if text:
                questions.append({"text": text, "qtype": qtype, "required": required, "options": options})
                request.session["survey_questions"] = questions
                request.session.modified = True
                messages.success(request, "Pregunta agregada.")
            else:
                messages.error(request, "El texto de la pregunta es requerido.")

        elif action == "delete":
            try:
                idx = int(request.POST.get("index", "-1"))
                if 0 <= idx < len(questions):
                    questions.pop(idx)
                    request.session["survey_questions"] = questions
                    request.session.modified = True
                    messages.success(request, "Pregunta eliminada.")
            except ValueError:
                pass

        return redirect("surveys:create_step_2")


# ======================================
# Paso 3: Revisión y publicación final
# ======================================
@method_decorator(login_required, name="dispatch")
class Step3Review(View):
    template_name = "surveys/create_step_3.html"

    def get(self, request):
        basic = request.session.get("survey_basic")
        questions = request.session.get("survey_questions", [])

        if not basic:
            messages.info(request, "Primero completa la información básica.")
            return redirect("surveys:create_step_1")
        if not questions:
            messages.info(request, "Agrega al menos una pregunta.")
            return redirect("surveys:create_step_2")

        draft = {"basic": basic, "questions": questions}
        context = {"draft": draft, "step": 3, "progress": 100}
        return render(request, self.template_name, context)

    def post(self, request):
        action = (request.POST.get("action") or "").lower().strip()
        if action == "back":
            return redirect("surveys:create_step_2")

        if action == "publish":
            # Aquí guardarías en BD real (Survey/Question) si ya tienes modelos.
            request.session.pop("survey_basic", None)
            request.session.pop("survey_questions", None)
            request.session.modified = True
            messages.success(request, "Encuesta publicada correctamente.")
            return redirect("surveys:create_step_1")

        return redirect("surveys:create_step_3")
