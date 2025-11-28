import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE','byteneko.settings')
import django
django.setup()
from surveys.models import Survey, SurveyResponse
from core.services.survey_analysis import SurveyAnalysisService
import json

# Change this id to test a specific survey
SURVEY_ID = 197
s = Survey.objects.filter(pk=SURVEY_ID).first()
if not s:
    print('Survey not found:', SURVEY_ID)
    s = Survey.objects.order_by('-id').first()
    print('Trying latest survey id', s.id if s else 'none')

responses_qs = SurveyResponse.objects.filter(survey=s)
res = SurveyAnalysisService.get_analysis_data(s, responses_qs, include_charts=True)
out = []
for q in res.get('analysis_data', []):
    out.append({
        'id': q.get('id'),
        'type': q.get('type'),
        'chart_data_len': len(q.get('chart_data', {}).get('data', [])) if q.get('chart_data') else 0,
        'has_image': bool(q.get('chart_image'))
    })
print(json.dumps(out, indent=2, ensure_ascii=False))
