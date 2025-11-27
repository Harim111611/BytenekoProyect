# Generated manually on 2025-11-26 for English refactoring

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0008_alter_encuesta_categoria_alter_encuesta_estado_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Rename models
        migrations.RenameModel(
            old_name='Encuesta',
            new_name='Survey',
        ),
        migrations.RenameModel(
            old_name='Pregunta',
            new_name='Question',
        ),
        migrations.RenameModel(
            old_name='OpcionRespuesta',
            new_name='AnswerOption',
        ),
        migrations.RenameModel(
            old_name='RespuestaEncuesta',
            new_name='SurveyResponse',
        ),
        migrations.RenameModel(
            old_name='RespuestaPregunta',
            new_name='QuestionResponse',
        ),
        
        # Rename Survey fields
        migrations.RenameField(
            model_name='Survey',
            old_name='titulo',
            new_name='title',
        ),
        migrations.RenameField(
            model_name='Survey',
            old_name='descripcion',
            new_name='description',
        ),
        migrations.RenameField(
            model_name='Survey',
            old_name='categoria',
            new_name='category',
        ),
        migrations.RenameField(
            model_name='Survey',
            old_name='estado',
            new_name='status',
        ),
        migrations.RenameField(
            model_name='Survey',
            old_name='creador',
            new_name='author',
        ),
        migrations.RenameField(
            model_name='Survey',
            old_name='objetivo_muestra',
            new_name='sample_goal',
        ),
        migrations.RenameField(
            model_name='Survey',
            old_name='fecha_creacion',
            new_name='created_at',
        ),
        migrations.RenameField(
            model_name='Survey',
            old_name='fecha_modificacion',
            new_name='updated_at',
        ),
        
        # Rename Question fields
        migrations.RenameField(
            model_name='Question',
            old_name='encuesta',
            new_name='survey',
        ),
        migrations.RenameField(
            model_name='Question',
            old_name='texto',
            new_name='text',
        ),
        migrations.RenameField(
            model_name='Question',
            old_name='tipo',
            new_name='type',
        ),
        migrations.RenameField(
            model_name='Question',
            old_name='es_obligatoria',
            new_name='is_required',
        ),
        migrations.RenameField(
            model_name='Question',
            old_name='orden',
            new_name='order',
        ),
        
        # Rename AnswerOption fields
        migrations.RenameField(
            model_name='AnswerOption',
            old_name='pregunta',
            new_name='question',
        ),
        migrations.RenameField(
            model_name='AnswerOption',
            old_name='texto',
            new_name='text',
        ),
        
        # Rename SurveyResponse fields
        migrations.RenameField(
            model_name='SurveyResponse',
            old_name='encuesta',
            new_name='survey',
        ),
        migrations.RenameField(
            model_name='SurveyResponse',
            old_name='usuario',
            new_name='user',
        ),
        migrations.RenameField(
            model_name='SurveyResponse',
            old_name='creado_en',
            new_name='created_at',
        ),
        migrations.RenameField(
            model_name='SurveyResponse',
            old_name='anonima',
            new_name='is_anonymous',
        ),
        
        # Rename QuestionResponse fields
        migrations.RenameField(
            model_name='QuestionResponse',
            old_name='respuesta_encuesta',
            new_name='survey_response',
        ),
        migrations.RenameField(
            model_name='QuestionResponse',
            old_name='pregunta',
            new_name='question',
        ),
        migrations.RenameField(
            model_name='QuestionResponse',
            old_name='opcion',
            new_name='selected_option',
        ),
        migrations.RenameField(
            model_name='QuestionResponse',
            old_name='valor_texto',
            new_name='text_value',
        ),
        migrations.RenameField(
            model_name='QuestionResponse',
            old_name='valor_numerico',
            new_name='numeric_value',
        ),
        
        # Update table names
        migrations.AlterModelTable(
            name='Survey',
            table='surveys_survey',
        ),
        migrations.AlterModelTable(
            name='Question',
            table='surveys_question',
        ),
        migrations.AlterModelTable(
            name='AnswerOption',
            table='surveys_answeroption',
        ),
        migrations.AlterModelTable(
            name='SurveyResponse',
            table='surveys_surveyresponse',
        ),
        migrations.AlterModelTable(
            name='QuestionResponse',
            table='surveys_questionresponse',
        ),
        
        # Update Meta options
        migrations.AlterModelOptions(
            name='Survey',
            options={
                'verbose_name': 'Encuesta',
                'verbose_name_plural': 'Encuestas',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AlterModelOptions(
            name='Question',
            options={
                'verbose_name': 'Pregunta',
                'verbose_name_plural': 'Preguntas',
                'ordering': ['order'],
            },
        ),
        migrations.AlterModelOptions(
            name='AnswerOption',
            options={
                'verbose_name': 'Opción de Respuesta',
                'verbose_name_plural': 'Opciones de Respuesta',
            },
        ),
        migrations.AlterModelOptions(
            name='SurveyResponse',
            options={
                'verbose_name': 'Respuesta de Encuesta',
                'verbose_name_plural': 'Respuestas de Encuestas',
            },
        ),
        migrations.AlterModelOptions(
            name='QuestionResponse',
            options={
                'verbose_name': 'Respuesta de Pregunta',
                'verbose_name_plural': 'Respuestas de Preguntas',
            },
        ),
    ]
