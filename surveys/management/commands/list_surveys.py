from django.core.management.base import BaseCommand
from surveys.models import Survey

class Command(BaseCommand):
    help = 'List surveys (id, title)'

    def handle(self, *args, **options):
        for s in Survey.objects.all().order_by('id'):
            self.stdout.write(f"{s.id}\t{s.title}")
