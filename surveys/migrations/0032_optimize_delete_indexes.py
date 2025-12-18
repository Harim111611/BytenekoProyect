# surveys/migrations/0XXX_optimize_delete_indexes.py
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0031_alter_answeroption_order_alter_answeroption_question_and_more'),
    ]

    operations = [
        # Índice compuesto en QuestionResponse.survey_response_id para optimizar
        # DELETE FROM questionresponse WHERE survey_response_id IN (SELECT id FROM surveyresponse...)
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS idx_qr_survey_response_delete 
            ON surveys_questionresponse(survey_response_id);
            """,
            reverse_sql="DROP INDEX IF EXISTS idx_qr_survey_response_delete;"
        ),
        
        # Índice en SurveyResponse.survey_id para optimizar
        # DELETE FROM surveyresponse WHERE survey_id = ANY(...)
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS idx_sr_survey_delete 
            ON surveys_surveyresponse(survey_id);
            """,
            reverse_sql="DROP INDEX IF EXISTS idx_sr_survey_delete;"
        ),
        
        # Índice en Question.survey_id para optimizar
        # SELECT id FROM question WHERE survey_id = ANY(...)
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS idx_question_survey_delete 
            ON surveys_question(survey_id);
            """,
            reverse_sql="DROP INDEX IF EXISTS idx_question_survey_delete;"
        ),
        
        # Índice en AnswerOption.question_id para optimizar
        # DELETE FROM answeroption WHERE question_id IN (SELECT id FROM question...)
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS idx_ao_question_delete 
            ON surveys_answeroption(question_id);
            """,
            reverse_sql="DROP INDEX IF EXISTS idx_ao_question_delete;"
        ),
        
        # Índice en ImportJob.survey_id para optimizar
        # DELETE FROM importjob WHERE survey_id = ANY(...)
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS idx_ij_survey_delete 
            ON surveys_importjob(survey_id);
            """,
            reverse_sql="DROP INDEX IF EXISTS idx_ij_survey_delete;"
        ),
    ]
