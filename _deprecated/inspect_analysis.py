import os
import sys

if len(sys.argv) < 2:
    print('Usage: python inspect_analysis.py <survey_id>')
    sys.exit(1)

survey_id = int(sys.argv[1])

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'byteneko.settings.production')
import django
django.setup()

from surveys.models import Survey
from core.services.survey_analysis import SurveyAnalysisService

survey = Survey.objects.filter(pk=survey_id).first()
if not survey:
    print('Survey not found', survey_id)
    sys.exit(1)

responses_qs = survey.surveyresponse_set.all()
print('Total responses for survey', survey_id, responses_qs.count())
res = SurveyAnalysisService.get_analysis_data(survey, responses_qs, include_charts=True)
print('nps_data keys:', res.get('nps_data') is not None)
for item in res.get('analysis_data', []):
    print('Question', item['id'], item['text'][:50])
    print(' type:', item['type'])
    print(' total_respuestas:', item.get('total_respuestas'))
    print(' chart_labels len:', len(item.get('chart_labels') or []))
    print(' chart_data len:', len(item.get('chart_data') or []))
    print(' chart_image present:', bool(item.get('chart_image')))
    print('---')

print('heatmap present:', bool(res.get('heatmap_image')))
