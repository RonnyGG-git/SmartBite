from django.core.management.base import BaseCommand

from caja.models import MetodoPago
from cuentas.models import ROLES_SISTEMA, Rol


class Command(BaseCommand):
    help = "Crea los datos base indispensables: roles del sistema y métodos de pago."

    def handle(self, *args, **options):
        for clave, _ in ROLES_SISTEMA:
            _, creado = Rol.objects.get_or_create(nombre=clave)
            if creado:
                self.stdout.write(self.style.SUCCESS(f"Rol creado: {clave}"))

        for nombre in ["Efectivo", "Tarjeta", "Transferencia", "Billetera Digital"]:
            _, creado = MetodoPago.objects.get_or_create(nombre=nombre)
            if creado:
                self.stdout.write(self.style.SUCCESS(f"Método de pago creado: {nombre}"))

        self.stdout.write(self.style.SUCCESS("Datos base listos."))
