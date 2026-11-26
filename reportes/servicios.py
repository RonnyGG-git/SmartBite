from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from caja.models import Pago
from core.tenancy import filtrar, restaurante_actual
from inventario.models import ItemInventario
from operativo.models import DetalleOrden, Orden

CERO = Decimal("0")
MAXIMO_DIAS = 366


class PeriodoInvalido(ValueError):
    pass


def _leer_fecha(texto, nombre):
    try:
        return date.fromisoformat(texto)
    except (TypeError, ValueError):
        raise PeriodoInvalido(f"La fecha «{nombre}» no es válida. Usa el formato AAAA-MM-DD.")


def leer_periodo(desde_texto, hasta_texto):
    hoy = timezone.localdate()
    desde = _leer_fecha(desde_texto, "desde") if desde_texto else hoy.replace(day=1)
    hasta = _leer_fecha(hasta_texto, "hasta") if hasta_texto else hoy
    if desde > hasta:
        raise PeriodoInvalido("La fecha inicial no puede ser posterior a la final.")
    if (hasta - desde).days >= MAXIMO_DIAS:
        raise PeriodoInvalido("El periodo no puede superar un año.")
    return desde, hasta


def datos_reporte(request, desde, hasta):
    rango = (desde, hasta)
    ordenes = filtrar(Orden.objects, request, "sucursal__restaurante").filter(creado_en__date__range=rango)
    pagos = filtrar(Pago.objects, request, "orden__sucursal__restaurante").filter(
        estado=Pago.APROBADO, creado_en__date__range=rango
    )
    totales = pagos.aggregate(ventas=Sum("monto"), propinas=Sum("propina"))
    ventas = totales["ventas"] or CERO
    ordenes_cobradas = pagos.values("orden").distinct().count()

    por_estado = dict(ordenes.values_list("estado").annotate(cantidad=Count("pk")))
    subtotal = ExpressionWrapper(F("cantidad") * F("precio_unitario"), output_field=DecimalField(max_digits=14, decimal_places=2))
    productos = (
        DetalleOrden.objects.filter(orden__in=ordenes.exclude(estado=Orden.CANCELADA))
        .values("producto__nombre")
        .annotate(unidades=Sum("cantidad"), total=Sum(subtotal))
        .order_by("-unidades", "producto__nombre")[:10]
    )
    items = filtrar(ItemInventario.objects, request, "sucursal__restaurante").select_related("sucursal")

    return {
        "restaurante": restaurante_actual(request),
        "desde": desde,
        "hasta": hasta,
        "generado_en": timezone.localtime(),
        "generado_por": getattr(request.user, "nombre", "") or str(request.user),
        "ventas": ventas,
        "propinas": totales["propinas"] or CERO,
        "numero_pagos": pagos.count(),
        "ordenes": ordenes.count(),
        "ordenes_cobradas": ordenes_cobradas,
        "ticket_promedio": (ventas / ordenes_cobradas) if ordenes_cobradas else CERO,
        "ordenes_por_estado": [
            {"estado": estado, "nombre": nombre, "cantidad": por_estado.get(estado, 0)}
            for estado, nombre in Orden.ESTADO_CHOICES
        ],
        "ventas_por_metodo": list(
            pagos.values("metodo_pago__nombre").annotate(total=Sum("monto"), pagos=Count("pk")).order_by("-total")
        ),
        "ventas_por_dia": list(
            pagos.annotate(dia=TruncDate("creado_en")).values("dia").annotate(total=Sum("monto"), pagos=Count("pk")).order_by("dia")
        ),
        "productos_mas_vendidos": list(productos),
        "stock_bajo": [item for item in items if item.stock_bajo],
    }


def nombre_archivo(desde, hasta):
    return f"reporte-smartbite-{desde.isoformat()}-a-{hasta.isoformat()}.pdf"
