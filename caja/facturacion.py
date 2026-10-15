"""Emisión del comprobante de venta (SIMULADO: sin validez fiscal ante la DIAN).

Supuesto: los precios del menú YA incluyen el impuesto al consumo (INC) del 8 %, como exige
la norma para restaurantes; por eso el INC se desglosa del total, no se suma. La propina es
voluntaria: va aparte y nunca entra en la base del impuesto."""
import hashlib
from decimal import Decimal

from django.db.models import Max
from django.utils import timezone

from .models import Factura, Pago

CERO = Decimal("0")
TASA_INC = Decimal("0.08")
CENTAVOS = Decimal("0.01")
DOCUMENTO_CONSUMIDOR_FINAL = "222222222222"


def desglose_inc(total):
    """Del total con INC incluido devuelve (base gravable, INC)."""
    total = Decimal(total)
    base = (total / (1 + TASA_INC)).quantize(CENTAVOS)
    return base, total - base


def emitir_factura(orden):
    """Crea (una sola vez) el comprobante de una orden ya pagada."""
    existente = Factura.objects.filter(orden=orden).first()
    if existente:
        return existente

    pagos = list(orden.pagos.filter(estado=Pago.APROBADO).select_related("metodo_pago").order_by("creado_en"))
    detalles = list(orden.detalles.select_related("producto"))
    total = Decimal(orden.total)
    base, inc = desglose_inc(total)
    propina = sum((p.propina for p in pagos), CERO)
    cliente = orden.cliente
    sucursal = orden.mesa.sucursal
    restaurante = sucursal.restaurante

    numero = (Factura.objects.aggregate(m=Max("numero"))["m"] or 0) + 1
    codigo = f"{Factura.PREFIJO}-{numero:06d}"
    cufe = hashlib.sha384(
        f"{codigo}|{timezone.now().isoformat()}|{base}|{inc}|{total}|{restaurante.nif}".encode()
    ).hexdigest()

    return Factura.objects.create(
        orden=orden,
        numero=numero,
        cliente_nombre=cliente.nombre if cliente else "Consumidor final",
        cliente_documento=(cliente.numero_documento if cliente and cliente.numero_documento else DOCUMENTO_CONSUMIDOR_FINAL),
        cliente_email=cliente.email if cliente else "",
        base_gravable=base,
        inc=inc,
        total_consumo=total,
        propina=propina,
        total_pagado=total + propina,
        cufe=cufe,
        detalle={
            "emisor": {
                "nombre": restaurante.nombre, "nit": restaurante.nif,
                "direccion": sucursal.direccion or restaurante.direccion,
                "telefono": sucursal.telefono or restaurante.telefono,
                "sucursal": sucursal.nombre,
            },
            "mesa": orden.mesa.numero,
            "lineas": [
                {"nombre": d.producto.nombre, "cantidad": d.cantidad,
                 "precio_unitario": str(d.precio_unitario), "subtotal": str(d.subtotal)}
                for d in detalles
            ],
            "pagos": [
                {"metodo": p.metodo_pago.nombre, "monto": str(p.monto), "propina": str(p.propina),
                 "referencia": p.referencia_transaccion}
                for p in pagos
            ],
        },
    )