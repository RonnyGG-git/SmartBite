from decimal import Decimal

from . import conf, servicios
from .models import AuditoriaCobro, EnlacePago, MetodoPago
from .pasarelas import SimuladaPasarela, obtener_pasarela
from .servicios import CobroInvalido

CERO = Decimal("0")
METODO_QR = "Pago QR"


def obtener_enlace_pago(orden, usuario=None):
    from django.utils import timezone

    enlace = orden.enlaces_pago.filter(expira_en__gt=timezone.now()).order_by("-creado_en").first()
    return enlace or EnlacePago.objects.create(orden=orden, creado_por=usuario)


def cobrar_por_qr(enlace, *, monto, propina=CERO, ip=None):
    if not enlace.vigente:
        raise CobroInvalido("Este código QR venció. Pide uno nuevo en caja.")
    metodo, _ = MetodoPago.objects.get_or_create(nombre=METODO_QR, defaults={"activo": False})
    pasarela = SimuladaPasarela()
    pago, _ = servicios.iniciar_cobro_tarjeta(
        enlace.orden_id, metodo=metodo, monto=monto, propina=propina, usuario=None, ip=ip,
        pasarela=pasarela, origen="QR",
    )
    servicios.procesar_evento(pasarela, pasarela.construir_evento(pago, "APPROVED"), {})
    pago.refresh_from_db()
    return pago


def pedir_pago_en_efectivo(enlace):
    from django.utils import timezone

    if not enlace.vigente:
        raise CobroInvalido("Este código QR venció. Pide uno nuevo en caja.")
    ahora = timezone.now()
    if enlace.efectivo_solicitado_en is None:
        enlace.efectivo_solicitado_en = ahora
        enlace.save(update_fields=["efectivo_solicitado_en", "actualizado_en"])
    orden = enlace.orden
    if orden.cuenta_solicitada_en is None:
        orden.cuenta_solicitada_en = ahora
        orden.save(update_fields=["cuenta_solicitada_en", "actualizado_en"])
    servicios.auditar(AuditoriaCobro.EFECTIVO_SOLICITADO, orden, detalle="El cliente pagará en efectivo en caja")
    return enlace


def es_simulada():
    return conf.proveedor() == "SIMULADA"


def iniciar_cobro_qr(enlace, *, monto, propina=CERO, ip=None):
    if not enlace.vigente:
        raise CobroInvalido("Este código QR venció. Pide uno nuevo en caja.")
    metodo, _ = MetodoPago.objects.get_or_create(nombre=METODO_QR, defaults={"activo": False})
    return servicios.iniciar_cobro_tarjeta(
        enlace.orden_id, metodo=metodo, monto=monto, propina=propina, usuario=None, ip=ip,
        pasarela=obtener_pasarela(), origen="QR",
    )