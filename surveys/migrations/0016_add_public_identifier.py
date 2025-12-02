from django.db import migrations, models


def populate_public_id(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    db_alias = schema_editor.connection.alias

    counters = {}
    batch = []

    def flush_batch():
        nonlocal batch
        if not batch:
            return
        Survey.objects.using(db_alias).bulk_update(batch, ['author_sequence', 'public_id'])
        batch = []

    for survey in Survey.objects.using(db_alias).select_related('author').order_by('author_id', 'created_at', 'pk'):
        author_id = survey.author_id
        if not author_id:
            continue
        counters[author_id] = counters.get(author_id, 0) + 1
        seq = counters[author_id]
        survey.author_sequence = seq
        survey.public_id = f"SUR-{author_id:03d}-{seq:04d}"
        batch.append(survey)
        if len(batch) >= 200:
            flush_batch()

    flush_batch()


def revert_public_id(apps, schema_editor):
    Survey = apps.get_model('surveys', 'Survey')
    Survey.objects.all().update(author_sequence=None, public_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('surveys', '0015_add_is_imported_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='survey',
            name='author_sequence',
            field=models.PositiveIntegerField(blank=True, db_index=True, help_text='Número incremental de la encuesta para el autor', null=True, verbose_name='Author Sequence'),
        ),
        migrations.AddField(
            model_name='survey',
            name='public_id',
            field=models.CharField(blank=True, db_index=True, help_text='Identificador legible mostrado en URLs', max_length=20, null=True, unique=True, verbose_name='Public ID'),
        ),
        migrations.RunPython(populate_public_id, revert_public_id),
        migrations.AddConstraint(
            model_name='survey',
            constraint=models.UniqueConstraint(fields=('author', 'author_sequence'), name='survey_author_sequence_unique'),
        ),
    ]
