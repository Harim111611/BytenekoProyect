# surveys/admin.py
from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.db.models import Count
from django.urls import reverse
from .models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse, ImportJob

# --- 1. CONFIGURACIÓN DE BRANDING (Identidad Visual) ---
admin.site.site_header = "Administración Byteneko"
admin.site.site_title = "Byteneko Portal"
admin.site.index_title = "Panel de Control de Encuestas"
admin.site.enable_nav_sidebar = True  # Barra lateral de navegación moderna

# --- Inlines ---

class CsvLogInline(admin.TabularInline):
    """
    Permite ver el historial de importaciones CSV directamente 
    dentro de la ficha de la Encuesta.
    """
    model = ImportJob
    extra = 0
    fields = ('original_filename', 'status_pill_inline', 'created_at', 'processed_rows', 'error_message')
    readonly_fields = ('original_filename', 'status_pill_inline', 'created_at', 'processed_rows', 'error_message')
    can_delete = False
    show_change_link = True
    classes = ('collapse',)
    verbose_name = "Historial de Importación CSV"
    verbose_name_plural = "Historial de Importaciones CSV"

    def status_pill_inline(self, obj):
        colors = {
            'completed': 'green', 'failed': 'red', 
            'processing': 'orange', 'pending': 'gray'
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display().upper()
        )
    status_pill_inline.short_description = 'Estado'

class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 1
    fields = ('text', 'order', 'preview_usage')
    readonly_fields = ('preview_usage',)
    ordering = ['order']
    classes = ('collapse',)

    def preview_usage(self, obj):
        # CORRECCIÓN: Usamos 'questionresponse' en lugar de 'questionresponse_set'
        manager = getattr(obj, 'questionresponse', None) or getattr(obj, 'questionresponse_set', None)
        count = manager.count() if manager else 0
        return f"{count} selecciones"

class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    fields = ('text', 'type', 'is_required', 'order', 'is_demographic')
    ordering = ['order']
    show_change_link = True
    classes = ('collapse',)

class QuestionResponseInline(admin.TabularInline):
    model = QuestionResponse
    extra = 0
    fields = ('question', 'response_value')
    readonly_fields = ('question', 'response_value')
    can_delete = False
    max_num = 0

    def response_value(self, obj):
        if obj.selected_option:
            return obj.selected_option.text
        return obj.text_value or obj.numeric_value or "-"

# --- Model Admins ---

@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    # Optimización visual de la lista
    list_display = (
        'title', 
        'status_badge', 
        'progress_bar',  # Nueva barra visual
        'metrics_summary', # Nuevos contadores
        'author', 
        'created_at'
    )
    list_filter = ('status', 'category', 'created_at', 'author')
    search_fields = ('title', 'description', 'public_id')
    readonly_fields = ('created_at', 'updated_at', 'quick_analysis') # Nuevo panel de análisis
    
    # Django 5.0+: Muestra conteos en los filtros laterales
    show_facets = admin.ShowFacets.ALWAYS
    
    # AGREGADO: CsvLogInline para ver logs dentro de la encuesta
    inlines = [QuestionInline, CsvLogInline] 
    date_hierarchy = 'created_at'
    list_per_page = 20

    fieldsets = (
        ('🎯 Tablero Principal', {
            'fields': ('title', 'quick_analysis', 'status')
        }),
        ('⚙️ Configuración', {
            'fields': ('description', 'category', 'sample_goal', 'author', 'public_id'),
            'classes': ('collapse',),
        }),
        ('📅 Auditoría', {
            'fields': ('created_at', 'updated_at', 'is_imported'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _response_count=Count('responses', distinct=True),
            _question_count=Count('questions', distinct=True)
        )

    # --- Widgets Visuales ---

    @admin.display(description='Progreso')
    def progress_bar(self, obj):
        """Barra de progreso visual basada en la meta de muestra."""
        if obj.sample_goal <= 0:
            return "—"
        
        count = getattr(obj, '_response_count', obj.responses.count())
        percent = min((count / obj.sample_goal) * 100, 100)
        
        # Color dinámico: Rojo < 30%, Amarillo < 70%, Verde > 70%
        color = "#dc3545" if percent < 30 else "#ffc107" if percent < 70 else "#28a745"
        
        return format_html(
            '''
            <div style="width: 100px; background-color: #e9ecef; border-radius: 4px; overflow: hidden; display: inline-block; vertical-align: middle;">
                <div style="width: {}%; background-color: {}; height: 10px;"></div>
            </div>
            <span style="font-size: 11px; margin-left: 5px;">{:.0f}%</span>
            ''',
            percent,
            color,
            percent
        )

    @admin.display(description='Métricas')
    def metrics_summary(self, obj):
        """Muestra contadores clave en una sola columna."""
        resps = getattr(obj, '_response_count', 0)
        quest = getattr(obj, '_question_count', 0)
        return format_html(
            '<span title="Respuestas">📥 {}</span> &nbsp;|&nbsp; <span title="Preguntas">❓ {}</span>',
            resps,
            quest
        )

    @admin.display(description='Estado')
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',   # Gris
            'active': '#28a745',  # Verde
            'closed': '#343a40',  # Oscuro
            'paused': '#ffc107'   # Amarillo
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display().upper()
        )

    @admin.display(description='Análisis Rápido')
    def quick_analysis(self, obj):
        """
        Inyecta una tabla HTML dentro del formulario de detalle
        con los resultados preliminares.
        """
        total_responses = obj.responses.count()
        if total_responses == 0:
            return "Sin datos para analizar aún."

        # Obtenemos las primeras 5 preguntas para no saturar
        questions = obj.questions.all()[:5]

        rows = []
        for q in questions:
            # Lógica simple de visualización según tipo
            preview_html = "Texto libre / Numérico"
            if q.type in ['single', 'multi']:
                # Calcular top opción
                # CORRECCIÓN: Usamos 'questionresponse' en lugar de 'questionresponse_set'
                top_opt = AnswerOption.objects.filter(question=q)\
                    .annotate(num_answers=Count('questionresponse'))\
                    .order_by('-num_answers').first()
                if top_opt and top_opt.num_answers > 0:
                    pct = int((top_opt.num_answers / total_responses) * 100)
                    preview_html = format_html("Top: <strong>{}</strong> ({}%)", top_opt.text, pct)
                else:
                    preview_html = "Sin selecciones"

            question_text = (q.text[:40] + "...") if len(q.text) > 40 else q.text
            type_badge = format_html(
                '<span class="badge" style="background:#eee; padding:2px 5px;">{}</span>',
                q.get_type_display(),
            )
            rows.append(
                format_html(
                    "<tr>"
                    '<td style="padding: 5px; border-bottom: 1px solid #eee;">{}</td>'
                    '<td style="padding: 5px; border-bottom: 1px solid #eee;">{}</td>'
                    '<td style="padding: 5px; border-bottom: 1px solid #eee;">{}</td>'
                    "</tr>",
                    question_text,
                    type_badge,
                    preview_html,
                )
            )

        html_rows = format_html_join("", "{}", ((row,) for row in rows))

        return format_html(
            '''
            <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #17a2b8;">
                <h4 style="margin-top:0;">📊 Resumen Ejecutivo (Total: {})</h4>
                <table style="width:100%; font-size: 12px;">
                    <thead>
                        <tr style="text-align:left; color: #666;">
                            <th>Pregunta</th>
                            <th>Tipo</th>
                            <th>Tendencia</th>
                        </tr>
                    </thead>
                    <tbody>
                        {}
                    </tbody>
                </table>
                <p style="margin-bottom:0; margin-top:10px; font-size:11px; color:#666;">
                    * Mostrando primeras 5 preguntas.
                </p>
            </div>
            ''',
            total_responses,
            html_rows
        )


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text_short', 'survey_link', 'type_visual', 'is_required', 'stats_usage')
    list_filter = ('type', 'survey', 'is_analyzable')
    search_fields = ('text',)
    list_select_related = ('survey',)
    show_facets = admin.ShowFacets.ALWAYS
    inlines = [AnswerOptionInline]

    @admin.display(description='Pregunta')
    def text_short(self, obj):
        return (obj.text[:60] + '...') if len(obj.text) > 60 else obj.text

    @admin.display(description='Encuesta', ordering='survey')
    def survey_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            reverse('admin:surveys_survey_change', args=[obj.survey.id]),
            obj.survey.title
        )

    @admin.display(description='Tipo')
    def type_visual(self, obj):
        icons = {
            'text': '📝', 'number': '🔢', 'scale': '⚖️',
            'single': '🔘', 'multi': '☑️'
        }
        return f"{icons.get(obj.type, '')} {obj.get_type_display()}"

    @admin.display(description='Datos')
    def stats_usage(self, obj):
        # Muestra si tiene opciones
        count = obj.options.count()
        if count > 0:
            return f"{count} Opciones"
        return "Abierta"


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('id_visual', 'survey_link', 'user', 'created_at', 'completion_status')
    list_filter = ('survey', 'created_at', 'is_anonymous')
    date_hierarchy = 'created_at'
    inlines = [QuestionResponseInline]
    show_facets = admin.ShowFacets.ALWAYS
    
    @admin.display(description='ID')
    def id_visual(self, obj):
        return f"#{obj.id}"

    @admin.display(description='Encuesta')
    def survey_link(self, obj):
        return obj.survey.title

    @admin.display(description='Completado')
    def completion_status(self, obj):
        # Visual simple para ver si respondió algo
        answered = obj.question_responses.count()
        return format_html(
            '<span style="color:green;">✔ {} Respuestas</span>', answered
        ) if answered > 0 else format_html('<span style="color:red;">Vacío</span>')


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ('file_info', 'status_pill', 'survey_created', 'created_at')
    list_filter = ('status', 'created_at')
    readonly_fields = ('processed_rows', 'error_message', 'csv_file')
    show_facets = admin.ShowFacets.ALWAYS

    @admin.display(description='Archivo')
    def file_info(self, obj):
        name = obj.original_filename or obj.csv_file
        return format_html(
            '<strong>{}</strong><br><small>{}</small>', 
            name, 
            obj.survey_title or "-"
        )

    @admin.display(description='Estado')
    def status_pill(self, obj):
        colors = {
            'completed': 'green', 'failed': 'red', 
            'processing': 'orange', 'pending': 'gray'
        }
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px;">{}</span>',
            colors.get(obj.status, 'gray'),
            obj.get_status_display().upper()
        )

    @admin.display(description='Encuesta Generada')
    def survey_created(self, obj):
        if obj.survey:
            url = reverse('admin:surveys_survey_change', args=[obj.survey.id])
            return format_html('<a href="{}">Ver Encuesta ➡</a>', url)
        return "-"

@admin.register(AnswerOption)
class AnswerOptionAdmin(admin.ModelAdmin):
    list_display = ('text', 'question_preview', 'order', 'response_count')
    list_filter = ('question__type', 'question__survey')
    search_fields = ('text', 'question__text')
    
    def question_preview(self, obj):
        return obj.question.text[:50] + '...' if len(obj.question.text) > 50 else obj.question.text
    
    def response_count(self, obj):
        # CORRECCIÓN: Usamos 'questionresponse' en lugar de 'questionresponse_set'
        manager = getattr(obj, 'questionresponse', None) or getattr(obj, 'questionresponse_set', None)
        count = manager.count() if manager else 0
        return format_html('<strong>{}</strong> times selected', count)


@admin.register(QuestionResponse)
class QuestionResponseAdmin(admin.ModelAdmin):
    list_display = ('id', 'question', 'survey_response', 'selected_option', 'numeric_value', 'text_value')
    search_fields = (
        'question__text',
        'survey_response__survey__title',
        'text_value',
    )
    list_filter = ('question__type',)
    readonly_fields = ('question', 'survey_response', 'selected_option', 'numeric_value', 'text_value')