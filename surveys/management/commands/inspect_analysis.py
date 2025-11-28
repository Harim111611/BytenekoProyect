from django.core.management.base import BaseCommand
from surveys.models import Survey
from core.services.survey_analysis import SurveyAnalysisService

class Command(BaseCommand):
    help = 'Inspect analysis data for a given survey id'

    def add_arguments(self, parser):
        parser.add_argument('survey_id', type=int)

    def handle(self, *args, **options):
        survey_id = options['survey_id']
        survey = Survey.objects.filter(pk=survey_id).first()
        if not survey:
            self.stdout.write(self.style.ERROR(f'Survey {survey_id} not found'))
            return
        responses_qs = survey.responses.all()
        self.stdout.write(f'Total responses for survey {survey_id}: {responses_qs.count()}')
        res = SurveyAnalysisService.get_analysis_data(survey, responses_qs, include_charts=True)
        self.stdout.write(f"heatmap present: {bool(res.get('heatmap_image'))}")
        for item in res.get('analysis_data', []):
            self.stdout.write('-'*40)
            self.stdout.write(f"Question {item['id']}: {item['text'][:80]}")
            self.stdout.write(f" type: {item['type']}")
            self.stdout.write(f" total_respuestas: {item.get('total_respuestas')}")
            self.stdout.write(f" chart_labels len: {len(item.get('chart_labels') or [])}")
            self.stdout.write(f" chart_data len: {len(item.get('chart_data') or [])}")
            self.stdout.write(f" chart_image present: {bool(item.get('chart_image'))}")
