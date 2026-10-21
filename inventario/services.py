"""Servicios de inventario reutilizables.

Viven fuera de models.py para que el modelo no dependa de `recetas` (y así
`operativo.Orden` pueda usarlos sin risking imports circulares).
"""
import math
from collections import OrderedDict
from decimal import Decimal

from .models import MovimientoInventario


def calcular_insumos_requeridos(orden):
    """Total que la orden consume de inventario.

    Recorre los DetalleOrden y suma `cantidad_requerida * detalle.cantidad`
    por cada ProductoIngrediente activo. Agrega por ítem porque varios
    platillos de la misma orden pueden compartir un mismo insumo.

    Devuelve un OrderedDict[ItemInventario -> Decimal] en orden de aparición,
    que es estable y predecible para el log de movimientos.
    """
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
    """Descuenta del inventario lo que la orden consume según las recetas.

    Se invoca al entrar a EN_PREPARACION. La cantidad a restar por ítem es
    ceil(requerido) porque `cantidad_requerida` es Decimal(10,3) y
    `stock_actual` es entero: redondear hacia arriba evita Preparation que
    understatement el consumo (se redondearía al alza igual en cada uso, pero
    acumularía reales de desfase).

    Cuando no hay stock suficiente se recorta contra cero en vez de fallar:
    la cocina ya advierte los faltantes con `cocina.views.insumos_faltantes`
    y una orden en marcha no debe bloquearse por eso. Lo que faltó se devuelve
    en `faltantes` para que la vista pueda avisarlo.

    Devuelve un dict con:
        movimientos: [MovimientoInventario] generados (uno por ítem descontado).
        faltantes:   OrderedDict[ItemInventario -> unidades que no alcanzaron].
    """
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