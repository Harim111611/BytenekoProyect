# Generated migration to add demographic fields to Question
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0011_alter_answeroption_options_alter_question_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='is_demographic',
            field=models.BooleanField(default=False, verbose_name='Is Demographic', db_index=True),
        ),
        migrations.AddField(
            model_name='question',
            name='demographic_type',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Demographic Type', choices=[
                ('age', 'Edad'),
                ('gender', 'Género'),
                ('location', 'Ubicación'),
                ('occupation', 'Ocupación'),
                ('marital_status', 'Estado civil'),
                ('other', 'Otro'),
            ]),
        ),
    ]
