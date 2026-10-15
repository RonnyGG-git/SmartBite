"""Cobro desde el celular del cliente (pago por QR, simulado pero con el mismo recorrido
que una pasarela: se crea el pago PENDIENTE y llega un evento firmado que lo aprueba)."""
from decimal import Decimal

from . import servicios
from .models import EnlacePago, MetodoPago
from .pasarelas import SimuladaPasarela
from .servicios import CobroInvalido
from . import conf, servicios
from .pasarelas import SimuladaPasarela, obtener_pasarela

CERO = Decimal("0")
METODO_QR = "Pago QR"


def obtener_enlace_pago(orden, usuario=None):
    """Reusa el QR vigente de la orden o crea uno nuevo."""
    from django.utils import timezone

    enlace = orden.enlaces_pago.filter(expira_en__gt=timezone.now()).order_by("-creado_en").first()
    return enlace or EnlacePago.objects.create(orden=orden, creado_por=usuario)


def cobrar_por_qr(enlace, *, monto, propina=CERO, ip=None):
    if not enlace.vigente:
        raise CobroInvalido("Este código QR venció. Pide uno nuevo en caja.")
    # Método inactivo: no aparece en la lista del cajero, solo lo usa el flujo del QR.
    metodo, _ = MetodoPago.objects.get_or_create(nombre=METODO_QR, defaults={"activo": False})
    pasarela = SimuladaPasarela()
    pago, _ = servicios.iniciar_cobro_tarjeta(
        enlace.orden_id, metodo=metodo, monto=monto, propina=propina, usuario=None, ip=ip,
        pasarela=pasarela, origen="QR",
    )
    servicios.procesar_evento(pasarela, pasarela.construir_evento(pago, "APPROVED"), {})
    pago.refresh_from_db()
    return pago
def es_simulada():
    return conf.proveedor() == "SIMULADA"


def iniciar_cobro_qr(enlace, *, monto, propina=CERO, ip=None):
    """Con una pasarela real (Wompi): deja el pago PENDIENTE y devuelve (pago, pasarela).
    El cliente paga en el checkout de la pasarela y el webhook lo aprueba."""
    if not enlace.vigente:
        raise CobroInvalido("Este código QR venció. Pide uno nuevo en caja.")
    metodo, _ = MetodoPago.objects.get_or_create(nombre=METODO_QR, defaults={"activo": False})
    return servicios.iniciar_cobro_tarjeta(
        enlace.orden_id, metodo=metodo, monto=monto, propina=propina, usuario=None, ip=ip,
        pasarela=obtener_pasarela(), origen="QR",
    )