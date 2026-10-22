import math
from collections import OrderedDict
from decimal import Decimal

from .models import MovimientoInventario


def calcular_insumos_requeridos(orden):
    requerido = OrderedDict()
    detalles = orden.detalles.select_related("producto").prefetch_related(
        "producto__ingredientes__item_inventario"
    )
    for detalle in detalles:
        for ingrediente in detalle.producto.ingredientes.all():
            if not ingrediente.activo:
                continue
            item = ingrediente.item_inventario
            requerido[item] = requerido.get(item, Decimal("0")) + (
                ingrediente.cantidad_requerida * detalle.cantidad
            )
    return requerido


def descontar_insumos_por_receta(orden, motivo=None):
    motivo = motivo or f"Orden #{orden.id}"
    movimientos = []
    faltantes = OrderedDict()

    for item, cantidad in calcular_insumos_requeridos(orden).items():
        unidades = math.ceil(cantidad)
        if unidades <= 0:
            continue
        if item.stock_actual < unidades:
            faltantes[item] = unidades - item.stock_actual
        movimientos.append(
            item.ajustar_stock(MovimientoInventario.SALIDA, unidades, motivo)
        )

    return {"movimientos": movimientos, "faltantes": faltantes}