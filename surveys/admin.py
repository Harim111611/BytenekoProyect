# surveys/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import Survey, Question, AnswerOption, SurveyResponse, QuestionResponse


class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 1
    fields = ('text', 'order')
    ordering = ['order']


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0
    fields = ('text', 'type', 'is_required', 'order', 'is_demographic', 'demographic_type')
    ordering = ['order']
    show_change_link = True


class QuestionResponseInline(admin.TabularInline):
    model = QuestionResponse
    extra = 0
    fields = ('question', 'selected_option', 'numeric_value', 'text_value')
    readonly_fields = ('question', 'selected_option', 'numeric_value', 'text_value')
    can_delete = False
    max_num = 0  # No permitir agregar nuevos


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = (
        'title', 
        'status_badge', 
        'author', 
        'response_count',
        'category',
        'sample_goal',
        'completion_percentage',
        'created_at'
    )
    list_filter = ('status', 'category', 'created_at', 'author')
    search_fields = ('title', 'description', 'author__username')
    inlines = [QuestionInline]
    readonly_fields = ('created_at', 'updated_at', 'response_stats', 'question_count')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'category', 'status', 'author')
        }),
        ('Goals & Metrics', {
            'fields': ('sample_goal', 'response_stats', 'question_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _response_count=Count('responses', distinct=True),
            _question_count=Count('questions', distinct=True)
        )
    
    def status_badge(self, obj):
        colors = {
            'draft': '#6c757d',
            'active': '#28a745',
            'closed': '#dc3545'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px; font-size: 11px;">{}</span>',
            colors.get(obj.status, '#6c757d'),
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    def response_count(self, obj):
        count = obj._response_count if hasattr(obj, '_response_count') else obj.responses.count()
        return format_html('<strong>{}</strong>', count)
    response_count.short_description = 'Responses'
    response_count.admin_order_field = '_response_count'
    
    def question_count(self, obj):
        count = obj._question_count if hasattr(obj, '_question_count') else obj.questions.count()
        return format_html('{} questions', count)
    question_count.short_description = 'Questions'
    
    def completion_percentage(self, obj):
        if obj.sample_goal == 0:
            return '—'
        count = obj._response_count if hasattr(obj, '_response_count') else obj.responses.count()
        percentage = (count / obj.sample_goal) * 100
        color = '#28a745' if percentage >= 100 else '#ffc107' if percentage >= 50 else '#dc3545'
        return format_html(
            '<div style="width: 100px; background: #e9ecef; border-radius: 3px; overflow: hidden;">'
            '<div style="width: {}%; background: {}; padding: 2px 5px; color: white; font-size: 10px; text-align: center;">{}%</div>'
            '</div>',
            min(percentage, 100),
            color,
            int(percentage)
        )
    completion_percentage.short_description = 'Progress'
    
    def response_stats(self, obj):
        count = obj.responses.count()
        return format_html(
            '<strong>{}</strong> responses / <strong>{}</strong> goal',
            count,
            obj.sample_goal
        )
    response_stats.short_description = 'Response Statistics'

    def delete_model(self, request, obj):
        """Eliminación ultra-rápida usando SQL crudo, igual que en las vistas."""
        from django.db import transaction, connection
        from surveys.views.crud_views import _fast_delete_surveys
        from surveys.signals import DisableSignals
        from django.core.cache import cache
        survey_id = obj.id
        author_id = obj.author.id if obj.author else None
        with DisableSignals():
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        _fast_delete_surveys(cursor, [survey_id])
            except Exception as e:
                import logging
                logger = logging.getLogger('surveys')
                logger.error(f"[ADMIN] Error eliminando encuesta {survey_id}: {e}", exc_info=True)
                raise
        # Limpiar caché igual que en la vista
        if author_id:
            cache.delete(f"dashboard_data_user_{author_id}")
            try:
                cache.delete(f"survey_stats_{survey_id}")
            except Exception:
                pass

    def delete_queryset(self, request, queryset):
        """Eliminación ultra-rápida masiva desde el admin usando SQL crudo."""
        from django.db import transaction, connection
        from surveys.views.crud_views import _fast_delete_surveys
        from surveys.signals import DisableSignals
        from django.core.cache import cache
        survey_ids = list(queryset.values_list('id', flat=True))
        author_ids = list(queryset.values_list('author_id', flat=True))
        with DisableSignals():
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        _fast_delete_surveys(cursor, survey_ids)
            except Exception as e:
                import logging
                logger = logging.getLogger('surveys')
                logger.error(f"[ADMIN] Error eliminando encuestas {survey_ids}: {e}", exc_info=True)
                raise
        # Limpiar caché para todos los autores afectados
        for author_id, survey_id in zip(author_ids, survey_ids):
            if author_id:
                cache.delete(f"dashboard_data_user_{author_id}")
                try:
                    cache.delete(f"survey_stats_{survey_id}")
                except Exception:
                    pass


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('text_preview', 'survey_link', 'type_badge', 'order', 'is_required', 'is_demographic', 'demographic_type', 'option_count')
    list_filter = ('type', 'is_required', 'is_demographic', 'demographic_type', 'survey__status')
    search_fields = ('text', 'survey__title')
    inlines = [AnswerOptionInline]
    readonly_fields = ('option_count',)
    list_per_page = 50
    
    fieldsets = (
        ('Question Details', {
            'fields': ('survey', 'text', 'type', 'is_required', 'order', 'is_demographic', 'demographic_type')
        }),
        ('Statistics', {
            'fields': ('option_count',),
            'classes': ('collapse',)
        }),
    )
    
    def text_preview(self, obj):
        return obj.text[:60] + '...' if len(obj.text) > 60 else obj.text
    text_preview.short_description = 'Question Text'
    
    def survey_link(self, obj):
        url = reverse('admin:surveys_survey_change', args=[obj.survey.id])
        return format_html('<a href="{}">{}</a>', url, obj.survey.title)
    survey_link.short_description = 'Survey'
    
    def type_badge(self, obj):
        colors = {
            'text': '#6c757d',
            'number': '#007bff',
            'scale': '#17a2b8',
            'single': '#28a745',
            'multi': '#ffc107'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 10px;">{}</span>',
            colors.get(obj.type, '#6c757d'),
            obj.get_type_display()
        )
    type_badge.short_description = 'Type'
    type_badge.admin_order_field = 'type'
    
    def option_count(self, obj):
        count = obj.options.count()
        return format_html('{} options', count) if count > 0 else '—'
    option_count.short_description = 'Answer Options'


@admin.register(AnswerOption)
class AnswerOptionAdmin(admin.ModelAdmin):
    list_display = ('text', 'question_preview', 'order', 'response_count')
    list_filter = ('question__type', 'question__survey')
    search_fields = ('text', 'question__text')
    readonly_fields = ('response_count',)
    
    def question_preview(self, obj):
        return obj.question.text[:50] + '...' if len(obj.question.text) > 50 else obj.question.text
    question_preview.short_description = 'Question'
    
    def response_count(self, obj):
        count = obj.question_responses.count()
        return format_html('<strong>{}</strong> times selected', count)
    response_count.short_description = 'Usage'


@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'survey_link', 
        'user_display',
        'anonymous_badge',
        'answer_count',
        'created_at'
    )
    list_filter = ('survey', 'is_anonymous', 'created_at')
    search_fields = ('survey__title', 'user__username')
    readonly_fields = ('created_at', 'answer_count')
    inlines = [QuestionResponseInline]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Response Information', {
            'fields': ('survey', 'user', 'is_anonymous')
        }),
        ('Statistics', {
            'fields': ('answer_count', 'created_at')
        }),
    )
    
    def survey_link(self, obj):
        url = reverse('admin:surveys_survey_change', args=[obj.survey.id])
        return format_html('<a href="{}">{}</a>', url, obj.survey.title)
    survey_link.short_description = 'Survey'
    
    def user_display(self, obj):
        if obj.user:
            return obj.user.username
        return '—'
    user_display.short_description = 'User'
    
    def anonymous_badge(self, obj):
        if obj.is_anonymous:
            return format_html(
                '<span style="background-color: #6c757d; color: white; padding: 2px 8px; border-radius: 3px; font-size: 10px;">ANONYMOUS</span>'
            )
        return '—'
    anonymous_badge.short_description = 'Type'
    
    def answer_count(self, obj):
        count = obj.question_responses.count()
        return format_html('<strong>{}</strong> answers', count)
    answer_count.short_description = 'Answers'


@admin.register(QuestionResponse)
class QuestionResponseAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'survey_link',
        'question_preview',
        'response_value',
        'created_date'
    )
    list_filter = ('question__type', 'survey_response__survey', 'survey_response__created_at')
    search_fields = ('question__text', 'text_value', 'survey_response__survey__title')
    readonly_fields = ('survey_response', 'question', 'selected_option', 'numeric_value', 'text_value')
    date_hierarchy = 'survey_response__created_at'
    
    def survey_link(self, obj):
        url = reverse('admin:surveys_survey_change', args=[obj.survey_response.survey.id])
        return format_html('<a href="{}">{}</a>', url, obj.survey_response.survey.title)
    survey_link.short_description = 'Survey'
    
    def question_preview(self, obj):
        text = obj.question.text
        return text[:40] + '...' if len(text) > 40 else text
    question_preview.short_description = 'Question'
    
    def response_value(self, obj):
        if obj.selected_option:
            return format_html('<span style="color: #28a745;">✓ {}</span>', obj.selected_option.text)
        elif obj.numeric_value is not None:
            return format_html('<strong>{}</strong>', obj.numeric_value)
        elif obj.text_value:
            preview = obj.text_value[:50] + '...' if len(obj.text_value) > 50 else obj.text_value
            return format_html('<em>{}</em>', preview)
        return '—'
    response_value.short_description = 'Answer'
    
    def created_date(self, obj):
        return obj.survey_response.created_at
    created_date.short_description = 'Date'
    created_date.admin_order_field = 'survey_response__created_at'
