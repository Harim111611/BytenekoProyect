# surveys/views/__init__.py
"""
Survey views package.
Exports all views from submodules for convenient imports.
"""

# Import all views from submodules
from . import crud_views
from . import import_views
from . import report_views
from . import respond_views
from . import question_views

# Re-export class-based views from crud_views
from .crud_views import (
    SurveyListView,
    SurveyDetailView,
    SurveyCreateView,
    SurveyUpdateView,
    SurveyDeleteView,
    bulk_delete_surveys_view,
)

# Re-export function-based views from import_views
from .import_views import (
    import_survey_csv_async,
    import_job_status,
    import_csv_preview_view,
    import_responses_view,
)

# Re-export function-based views from report_views
from .report_views import (
    survey_results_view,
    export_survey_csv_view,
    survey_thanks_view,
    change_survey_status,
    debug_analysis_view,
    survey_analysis_ajax,
)

# Re-export function-based views from respond_views
from .respond_views import respond_survey_view

__all__ = [
    # Modules
    'crud_views',
    'import_views',
    'report_views',
    'respond_views',
    'question_views',
    
    # CRUD views
    'SurveyListView',
    'SurveyDetailView',
    'SurveyCreateView',
    'SurveyUpdateView',
    'SurveyDeleteView',
    'bulk_delete_surveys_view',
    
    # Import views
    'import_survey_csv_async',
    'import_job_status',
    'import_csv_preview_view',
    'import_responses_view',
    
    # Report views
    'survey_results_view',
    'export_survey_csv_view',
    'survey_thanks_view',
    'change_survey_status',
    'debug_analysis_view',
    'survey_analysis_ajax',
    
    # Respond views
    'respond_survey_view',
]