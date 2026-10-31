from django.core.management.base import BaseCommand

from operativo.models import Reserva
from operativo.services import sincronizar_reservas


class Command(BaseCommand):
    help = "Marca como reservadas las mesas con reserva próxima y cierra las reservas sin asistencia."

    def handle(self, *args, **options):
        antes = Reserva.objects.filter(estado=Reserva.NO_ASISTIO).count()
        sincronizar_reservas()
        cerradas = Reserva.objects.filter(estado=Reserva.NO_ASISTIO).count() - antes
        self.stdout.write(self.style.SUCCESS(f"Reservas actualizadas. Sin asistencia: {cerradas}."))
