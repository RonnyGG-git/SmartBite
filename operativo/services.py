from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from catalogo.models import Producto

from .models import Cliente, DetalleOrden, Orden

MAX_CANTIDAD_POR_LINEA = 50


def obtener_cliente(restaurante, nombre, telefono=""):
    nombre = (nombre or "").strip()[:150]
    if not nombre:
        return None
    existente = Cliente.objects.filter(
        restaurante=restaurante, nombre__iexact=nombre, telefono=telefono, email=""
    ).first()
    if existente:
        return existente
    try:
        with transaction.atomic():
            return Cliente.objects.create(nombre=nombre, telefono=telefono, restaurante=restaurante)
    except IntegrityError:
        return None


def crear_orden(sucursal, lineas, origen, tipo_consumo, cliente=None, mesa=None, estado=Orden.PENDIENTE):
    cantidades = {}
    for producto_id, cantidad in lineas:
        if not isinstance(cantidad, int) or not 1 <= cantidad <= MAX_CANTIDAD_POR_LINEA:
            raise ValidationError(f"Cantidad inválida: {cantidad}.")
        cantidades[producto_id] = cantidades.get(producto_id, 0) + cantidad
    if not cantidades:
        raise ValidationError("La orden no tiene productos.")
    if tipo_consumo not in dict(Orden.TIPO_CONSUMO_CHOICES):
        raise ValidationError("Tipo de consumo inválido.")

    with transaction.atomic():
        productos = {
            p.pk: p
            for p in Producto.objects.select_for_update().filter(
                pk__in=cantidades, sucursal=sucursal, disponible=True
            )
        }
        faltan = set(cantidades) - set(productos)
        if faltan:
            raise ValidationError(f"Productos no disponibles: {sorted(faltan)}.")
        orden = Orden.objects.create(
            sucursal=sucursal, mesa=mesa, cliente=cliente, origen=origen,
            tipo_consumo=tipo_consumo, estado=estado,
        )
        DetalleOrden.objects.bulk_create(
            DetalleOrden(orden=orden, producto=productos[pk], cantidad=c, precio_unitario=productos[pk].precio)
            for pk, c in cantidades.items()
        )
    return orden
