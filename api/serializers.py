from django.contrib.auth import authenticate
from rest_framework import serializers

from catalogo.models import Categoria, Producto
from inventario.models import ItemInventario, MovimientoInventario


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nombre"]


class ProductoMenuSerializer(serializers.ModelSerializer):
    categoria = CategoriaSerializer(read_only=True)

    class Meta:
        model = Producto
        fields = ["id", "nombre", "descripcion", "precio", "url_imagen", "categoria"]


class ItemInventarioSerializer(serializers.ModelSerializer):
    stock_bajo = serializers.BooleanField(read_only=True)

    class Meta:
        model = ItemInventario
        fields = [
            "id", "nombre", "descripcion", "unidad_medida", "stock_actual", "stock_minimo",
            "stock_bajo", "costo_unitario", "ubicacion", "sucursal",
        ]


class MovimientoInventarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInventario
        fields = ["id", "item", "tipo", "cantidad", "motivo", "creado_en"]


class AjusteStockSerializer(serializers.Serializer):
    """Mismos campos y límites que inventario.forms.AjusteStockForm."""

    tipo = serializers.ChoiceField(choices=MovimientoInventario.TIPO_CHOICES)
    cantidad = serializers.IntegerField(min_value=1)
    motivo = serializers.CharField(max_length=255)


class AjusteStockRespuestaSerializer(serializers.Serializer):
    item = ItemInventarioSerializer()
    movimiento = MovimientoInventarioSerializer()


class TokenSerializer(serializers.Serializer):
    """Email y contraseña del usuario (Usuario.USERNAME_FIELD es el email)."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        usuario = authenticate(
            request=self.context.get("request"), email=attrs["email"], password=attrs["password"]
        )
        if usuario is None:
            raise serializers.ValidationError("Email o contraseña incorrectos.", code="credenciales_invalidas")
        attrs["usuario"] = usuario
        return attrs


class TokenRespuestaSerializer(serializers.Serializer):
    token = serializers.CharField()
