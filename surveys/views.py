# surveys/views.py
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

from .forms import SurveyBasicForm, QuestionForm, QuestionType


# =========================
#  Plantillas por categoría
#  (alineadas al TSX de ejemplo)
# =========================
QUESTION_TEMPLATES = {
    "satisfaction": [
        "¿Qué tan satisfecho estás con nuestro producto/servicio?",
        "En una escala del 1 al 10, ¿cómo calificarías tu experiencia?",
        "¿Recomendarías nuestro producto/servicio a otras personas?",
        "¿Qué aspectos te gustan más de nuestro producto/servicio?",
        "¿Qué podríamos mejorar?",
    ],
    "product": [
        "¿Con qué frecuencia utilizas este producto?",
        "¿Qué características valoras más del producto?",
        "¿El producto cumple con tus expectativas?",
        "¿Qué precio estarías dispuesto a pagar?",
        "¿Qué alternativas has considerado?",
    ],
    "awareness": [
        "¿Has escuchado sobre nuestra marca anteriormente?",
        "¿Dónde nos conociste?",
        "¿Qué palabras asocias con nuestra marca?",
        "¿Conoces nuestros productos/servicios?",
        "¿Cómo describirías nuestra marca a un amigo?",
    ],
    "concept": [
        "¿Qué te parece este concepto?",
        "¿Es clara la propuesta de valor?",
        "¿Te interesaría adquirir este producto/servicio?",
        "¿Qué cambiarías del concepto?",
        "¿Para quién crees que es este producto/servicio?",
    ],
}

CATEGORY_LABEL = {
    "satisfaction": "Satisfacción del cliente",
    "product": "Investigación de producto",
    "awareness": "Brand awareness",
    "concept": "Test de concepto",
}


# Deducción rápida del tipo (como en el TSX: escala / recomendar / texto)
def _infer_type_from_text(t: str) -> str:
    low = t.lower()
    if "escala" in low or "calificarías" in low or "1 al 10" in low:
        return QuestionType.SCALE
    if "recomendarías" in low:
        return QuestionType.SINGLE
    return QuestionType.TEXT


# =========================
#  Paso 1: Información básica
# =========================
@method_decorator(login_required, name="dispatch")
@method_decorator(login_required, name="dispatch")
class CreateStep1View(View):
    template_name = "surveys/create_step_1.html"

    def get(self, request):
        initial = request.session.get("survey_basic", {})
        form = SurveyBasicForm(initial=initial)
        can_continue = bool(initial.get("name") and initial.get("category"))
        # 👇 NO mostramos el alert de éxito en GET
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "progress": 33,
                "can_continue": can_continue,  # habilita el botón si ya hay datos
                "saved_ok": False,             # ← siempre False en GET
            },
        )

    def post(self, request):
        form = SurveyBasicForm(request.POST)
        if form.is_valid():
            request.session["survey_basic"] = form.cleaned_data
            request.session.setdefault("survey_questions", [])
            request.session.modified = True
            messages.success(request, "¡Perfecto! Ya puedes continuar al siguiente paso.")
            return redirect("surveys:create_step_2")
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "progress": 33,
                "can_continue": False,
                "saved_ok": False,
            },
        )

    def post(self, request):
        form = SurveyBasicForm(request.POST)
        if form.is_valid():
            request.session["survey_basic"] = form.cleaned_data
            request.session.setdefault("survey_questions", [])
            request.session.modified = True
            # Nos quedamos en el paso 1 para mostrar la franja verde y habilitar el botón
            return render(
                request,
                self.template_name,
                {
                    "form": SurveyBasicForm(initial=form.cleaned_data),
                    "progress": 33,
                    "can_continue": True,
                    "saved_ok": True,
                },
            )
        return render(
            request,
            self.template_name,
            {"form": form, "progress": 33, "can_continue": False},
        )


# =========================
#  Paso 2: Agregar preguntas
# =========================
@method_decorator(login_required, name="dispatch")
class CreateStep2View(View):
    template_name = "surveys/create_step_2.html"

    def _base_ctx(self, request):
        basic = request.session.get("survey_basic", {})
        if not basic:
            return None

        category = basic.get("category")
        return {
            "progress": 67,
            "basic": basic,
            "category": category,
            "category_label": CATEGORY_LABEL.get(category, ""),
            "recommended": QUESTION_TEMPLATES.get(category, []),
            "questions": request.session.get("survey_questions", []),
        }

    def get(self, request):
        ctx = self._base_ctx(request)
        if ctx is None:
            messages.info(request, "Primero completa la información básica.")
            return redirect("surveys:create_step_1")

        # ¿Editar una pregunta existente?
        edit_idx = request.GET.get("edit")
        if edit_idx is not None:
            try:
                q = ctx["questions"][int(edit_idx)]
                form = QuestionForm(
                    initial={
                        "qtype": q.get("qtype", QuestionType.TEXT),
                        "text": q.get("text", ""),
                        "required": q.get("required", False),
                        # El form expone 'options' como textarea; en el clean lo convierte a options_list
                        "options": "\n".join(q.get("options", [])),
                    }
                )
                ctx.update({"form": form, "edit_idx": int(edit_idx)})
            except (ValueError, IndexError):
                pass

        return render(request, self.template_name, ctx)

    def post(self, request):
        basic = request.session.get("survey_basic")
        if not basic:
            return redirect("surveys:create_step_1")

        action = request.POST.get("action")
        questions = request.session.get("survey_questions", [])

        # 1) Agregar una sugerencia rápida (como en el TSX: botón "Agregar")
        if action == "quick_add":
            text = request.POST.get("q", "").strip()
            if text:
                qtype = _infer_type_from_text(text)
                questions.append(
                    {"qtype": qtype, "text": text, "required": False, "options": []}
                )
                request.session["survey_questions"] = questions
                request.session.modified = True
            return redirect("surveys:create_step_2")

        # 2) Guardar (crear o editar) una pregunta personalizada
        if action == "save":
            idx = request.POST.get("idx")
            form = QuestionForm(request.POST)
            if form.is_valid():
                data = form.cleaned_data
                qdict = {
                    "qtype": data["qtype"],
                    "text": data["text"],
                    "required": data["required"],
                    "options": data["options_list"],  # proviene del clean del form
                }
                if idx:
                    # editar
                    try:
                        questions[int(idx)] = qdict
                    except (ValueError, IndexError):
                        pass
                else:
                    # crear
                    questions.append(qdict)

                request.session["survey_questions"] = questions
                request.session.modified = True
                return redirect("surveys:create_step_2")

            # re-render con errores
            ctx = self._base_ctx(request)
            if ctx is None:
                return redirect("surveys:create_step_1")
            if request.POST.get("idx"):
                try:
                    ctx["edit_idx"] = int(request.POST.get("idx"))
                except ValueError:
                    pass
            ctx["form"] = form
            return render(request, self.template_name, ctx)

        # 3) Eliminar una pregunta
        if action == "remove":
            idx = request.POST.get("idx")
            try:
                questions.pop(int(idx))
                request.session["survey_questions"] = questions
                request.session.modified = True
            except (ValueError, IndexError):
                pass
            return redirect("surveys:create_step_2")

        # 4) Continuar a revisión (debe existir al menos 1 pregunta)
        if action == "continue":
            if questions:
                return redirect("surveys:create_step_3")
            ctx = self._base_ctx(request)
            if ctx is None:
                return redirect("surveys:create_step_1")
            ctx["must_add_one"] = True
            return render(request, self.template_name, ctx)

        # Fallback
        return redirect("surveys:create_step_2")


# =========================
#  Paso 3: Revisar y publicar
# =========================
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
        return render(request, self.template_name, {"draft": draft, "progress": 100})

    def post(self, request):
        action = request.POST.get("action", "")

        if action == "back":
            return redirect("surveys:create_step_2")

        if action == "publish":
            # TODO: Persistir en BD (Survey/Question) cuando definas tus modelos.
            # Ejemplo (pseudo):
            # survey = Survey.objects.create(
            #     name=basic["name"], category=basic["category"],
            #     description=basic.get("description",""), owner=request.user
            # )
            # for q in questions:
            #     Question.objects.create(
            #         survey=survey, text=q["text"], qtype=q["qtype"],
            #         required=q["required"], options=q["options"]
            #     )

            # Limpiar borrador de la sesión
            request.session.pop("survey_basic", None)
            request.session.pop("survey_questions", None)
            request.session.modified = True

            messages.success(request, "Encuesta publicada correctamente.")
            return redirect("dashboard")

        # Fallback
        return redirect("surveys:create_step_3")
