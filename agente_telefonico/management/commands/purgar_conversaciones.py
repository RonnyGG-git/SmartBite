from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from agente_telefonico.models import TurnoLlamada


class Command(BaseCommand):
    help = "Borra las transcripciones de llamadas más antiguas que la política de retención."

    def add_arguments(self, parser):
        parser.add_argument("--dias", type=int, default=None)

    def handle(self, *args, **opciones):
        dias = opciones["dias"] if opciones["dias"] is not None else settings.AGENTE_RETENCION_DIAS
        limite = timezone.now() - timedelta(days=dias)
        borrados, _ = TurnoLlamada.objects.filter(llamada__creado_en__lt=limite).delete()
        self.stdout.write(f"Transcripciones borradas: {borrados} (anteriores a {dias} días).")
