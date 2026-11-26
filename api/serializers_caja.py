from decimal import Decimal

from rest_framework import serializers

from caja.models import Factura, MetodoPago, Pago
from caja.servicios import saldo_disponible, saldo_pendiente

from .serializers_movil import OrdenSerializer


class MetodoPagoSerializer(serializers.ModelSerializer):
    usa_pasarela = serializers.BooleanField(source="requiere_pasarela", read_only=True)

    class Meta:
        model = MetodoPago
        fields = ["id", "nombre", "usa_pasarela"]


class PagoSerializer(serializers.ModelSerializer):
    metodo = serializers.CharField(source="metodo_pago.nombre", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    cobrado_por = serializers.CharField(source="cobrado_por.nombre", default=None, read_only=True)
    anulable = serializers.SerializerMethodField()

    class Meta:
        model = Pago
        fields = ["id", "metodo", "monto", "propina", "estado", "estado_nombre", "referencia_transaccion", "cobrado_por", "creado_en", "anulable"]

    def get_anulable(self, pago) -> bool:
        return pago.estado == Pago.PENDIENTE and bool(pago.proveedor)


class CuentaSerializer(serializers.Serializer):
    orden = OrdenSerializer(source="*")
    saldo_pendiente = serializers.SerializerMethodField()
    saldo_disponible = serializers.SerializerMethodField()
    cobrable = serializers.BooleanField(read_only=True)
    pagos = PagoSerializer(many=True, read_only=True)
    factura = serializers.SerializerMethodField()

    def get_saldo_pendiente(self, orden) -> str:
        return str(saldo_pendiente(orden))

    def get_saldo_disponible(self, orden) -> str:
        return str(max(saldo_disponible(orden), Decimal("0")))

    def get_factura(self, orden) -> int | None:
        factura = Factura.objects.filter(orden=orden).only("pk").first()
        return factura.pk if factura else None


class CobrarSerializer(serializers.Serializer):
    metodo = serializers.PrimaryKeyRelatedField(queryset=MetodoPago.objects.filter(activo=True))
    monto = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    propina = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))
    referencia = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    efectivo_recibido = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, allow_null=True)


class FacturaResumenSerializer(serializers.ModelSerializer):
    orden = serializers.IntegerField(source="orden_id", read_only=True)

    class Meta:
        model = Factura
        fields = ["id", "codigo", "orden", "cliente_nombre", "total_pagado", "creado_en"]


class FacturaSerializer(FacturaResumenSerializer):
    class Meta(FacturaResumenSerializer.Meta):
        fields = FacturaResumenSerializer.Meta.fields + [
            "cliente_documento", "cliente_email", "base_gravable", "inc", "total_consumo", "propina", "cufe", "detalle",
        ]
