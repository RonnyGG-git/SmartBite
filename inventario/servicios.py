from django.db import transaction

from .models import Compra, MovimientoInventario


def recibir_compra(compra):
    if compra.estado != Compra.PENDIENTE:
        return False
    with transaction.atomic():
        for detalle in compra.detalles.select_related("item"):
            detalle.item.stock_actual += detalle.cantidad
            detalle.item.save(update_fields=["stock_actual"])
            MovimientoInventario.objects.create(
                item=detalle.item,
                tipo=MovimientoInventario.ENTRADA,
                cantidad=detalle.cantidad,
                motivo=f"Recepción compra #{compra.pk}",
            )
        compra.estado = Compra.RECIBIDA
        compra.save(update_fields=["estado"])
    return True


def anular_compra(compra):
    if compra.estado != Compra.PENDIENTE:
        return False
    compra.estado = Compra.ANULADA
    compra.save(update_fields=["estado"])
    return True
