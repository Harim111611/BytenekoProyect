# Generated migration for delete optimization
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0012_add_demographic_fields'),
    ]

    operations = [
        # Índice para optimizar DELETE de QuestionResponse por survey_response_id
        # NOTA: Para test/CI, quitar CONCURRENTLY (no permitido en transacciones)
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS 
                qresponse_survey_response_idx 
                ON surveys_questionresponse (survey_response_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS qresponse_survey_response_idx;
            """,
        ),
        # Índice para optimizar DELETE de QuestionResponse por question_id
        migrations.RunSQL(
            sql="""
                CREATE INDEX IF NOT EXISTS 
                qresponse_question_only_idx 
                ON surveys_questionresponse (question_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS qresponse_question_only_idx;
            """,
        ),
    ]


