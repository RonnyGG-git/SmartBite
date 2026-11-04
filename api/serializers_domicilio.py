from rest_framework import serializers

from domicilio.models import DireccionCliente, Domicilio
from operativo.models import Orden

from .serializers_movil import LineaPedidoSerializer, OrdenSerializer, RegistroSerializer


class RegistroClienteSerializer(RegistroSerializer):
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)


class PerfilClienteSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150)
    email = serializers.EmailField(read_only=True)
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)
    documento = serializers.CharField(max_length=30, required=False, allow_blank=True)


class DireccionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DireccionCliente
        fields = ["id", "etiqueta", "direccion", "referencia", "latitud", "longitud", "principal"]


class PuntoSerializer(serializers.Serializer):
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)


class EntregarSerializer(serializers.Serializer):
    codigo = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "El código tiene 4 números."})


class PedidoDomicilioSerializer(serializers.Serializer):
    sucursal = serializers.IntegerField()
    direccion = serializers.IntegerField()
    telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)
    lineas = LineaPedidoSerializer(many=True, allow_empty=False)


class PedidoMesaSerializer(serializers.Serializer):
    tipo_consumo = serializers.ChoiceField(choices=[Orden.EN_RESTAURANTE, Orden.PARA_LLEVAR])
    nombre = serializers.CharField(max_length=150, required=False, allow_blank=True)
    lineas = LineaPedidoSerializer(many=True, allow_empty=False)


class DomicilioSerializer(serializers.ModelSerializer):
    orden = OrdenSerializer(read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    cliente = serializers.CharField(source="cliente.nombre", read_only=True)
    domiciliario = serializers.CharField(source="domiciliario.nombre", default=None, read_only=True)
    sucursal = serializers.SerializerMethodField()

    class Meta:
        model = Domicilio
        fields = [
            "id", "orden", "estado", "estado_nombre", "cliente", "telefono", "direccion", "referencia",
            "latitud", "longitud", "domiciliario", "lat_actual", "lng_actual", "ubicacion_en",
            "asignado_en", "recogido_en", "entregado_en", "creado_en", "sucursal",
        ]

    def get_sucursal(self, d) -> dict:
        s = d.orden.sucursal
        return {
            "id": s.pk, "nombre": s.nombre, "restaurante": s.restaurante.nombre, "direccion": s.direccion,
            "latitud": s.latitud, "longitud": s.longitud,
        }


class DomicilioClienteSerializer(DomicilioSerializer):
    """El cliente ve además su código de entrega: se lo dicta al domiciliario al recibir."""

    class Meta(DomicilioSerializer.Meta):
        fields = DomicilioSerializer.Meta.fields + ["codigo_entrega"]
