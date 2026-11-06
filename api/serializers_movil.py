from rest_framework import serializers

from catalogo.models import Producto
from cliente.forms import MAX_CANTIDAD_POR_PRODUCTO
from cuentas.models import Usuario
from operativo.models import DetalleOrden, Mesa, Orden, Reserva
from restaurantes.models import Restaurante, Sucursal

from .serializers import CategoriaSerializer


class RestauranteResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurante
        fields = ["id", "nombre"]


class PerfilSerializer(serializers.ModelSerializer):
    rol = serializers.SerializerMethodField()
    rol_nombre = serializers.SerializerMethodField()
    es_superusuario = serializers.BooleanField(source="is_superuser")
    restaurantes = serializers.SerializerMethodField()
    restaurante_actual = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = ["id", "nombre", "email", "rol", "rol_nombre", "es_superusuario", "restaurantes", "restaurante_actual"]

    def get_rol(self, usuario):
        return usuario.rol.nombre if usuario.rol_id else None

    def get_rol_nombre(self, usuario):
        return usuario.rol.get_nombre_display() if usuario.rol_id else None

    def get_restaurantes(self, usuario):
        return RestauranteResumenSerializer(self.context["restaurantes"], many=True).data

    def get_restaurante_actual(self, usuario):
        actual = self.context.get("restaurante_actual")
        return RestauranteResumenSerializer(actual).data if actual else None


class SesionSerializer(serializers.Serializer):
    token = serializers.CharField()
    usuario = PerfilSerializer()


class RegistroSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)


class RegistroEmpleadoSerializer(RegistroSerializer):
    codigo = serializers.CharField(max_length=20)


class EmailSerializer(serializers.Serializer):
    email = serializers.EmailField()


class VerificarSerializer(EmailSerializer):
    codigo = serializers.RegexField(r"^\d{4}$", error_messages={"invalid": "Escribe los 4 números del código."})


class RestablecerSerializer(VerificarSerializer):
    password1 = serializers.CharField(write_only=True)
    password2 = serializers.CharField(write_only=True)


class MensajeSerializer(serializers.Serializer):
    detail = serializers.CharField()


class MesaResumenSerializer(serializers.ModelSerializer):
    class Meta:
        model = Mesa
        fields = ["id", "numero"]


class DetalleOrdenSerializer(serializers.ModelSerializer):
    producto = serializers.IntegerField(source="producto_id", read_only=True)
    nombre = serializers.CharField(source="producto.nombre", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = DetalleOrden
        fields = ["id", "producto", "nombre", "cantidad", "precio_unitario", "subtotal"]


class OrdenSerializer(serializers.ModelSerializer):
    mesa = MesaResumenSerializer(read_only=True)
    cliente = serializers.CharField(source="cliente.nombre", default=None, read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    origen_nombre = serializers.CharField(source="get_origen_display", read_only=True)
    tipo_consumo_nombre = serializers.CharField(source="get_tipo_consumo_display", read_only=True)
    ubicacion = serializers.CharField(read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    pagada = serializers.BooleanField(read_only=True)
    listo_estimado_en = serializers.DateTimeField(read_only=True)
    detalles = DetalleOrdenSerializer(many=True, read_only=True)

    class Meta:
        model = Orden
        fields = [
            "id", "estado", "estado_nombre", "origen", "origen_nombre", "tipo_consumo", "tipo_consumo_nombre",
            "ubicacion", "mesa", "sucursal", "cliente", "total", "pagada", "tiempo_estimado_min",
            "preparacion_iniciada_en", "listo_estimado_en", "cuenta_solicitada_en", "creado_en", "detalles",
        ]


class OrdenCocinaSerializer(OrdenSerializer):
    faltantes = serializers.SerializerMethodField()

    class Meta(OrdenSerializer.Meta):
        fields = OrdenSerializer.Meta.fields + ["faltantes"]

    def get_faltantes(self, orden) -> list[str]:
        from cocina.views import insumos_faltantes

        return [item.nombre for item in insumos_faltantes(orden)]


class MesaSerializer(serializers.ModelSerializer):
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    orden_activa = serializers.SerializerMethodField()

    class Meta:
        model = Mesa
        fields = ["id", "numero", "capacidad", "estado", "estado_nombre", "sucursal", "sucursal_nombre", "orden_activa"]

    def get_orden_activa(self, mesa) -> dict | None:
        orden = mesa.orden_activa
        if orden is None:
            return None
        return {
            "id": orden.pk,
            "estado": orden.estado,
            "estado_nombre": orden.get_estado_display(),
            "total": str(orden.total),
            "cuenta_solicitada": orden.cuenta_solicitada_en is not None,
        }


class ReservaSerializer(serializers.ModelSerializer):
    mesa = MesaResumenSerializer(read_only=True)

    class Meta:
        model = Reserva
        fields = ["id", "codigo", "mesa", "fecha_hora", "num_personas", "nombre", "telefono", "estado"]


class ProductoSerializer(serializers.ModelSerializer):
    categoria = CategoriaSerializer(read_only=True)

    class Meta:
        model = Producto
        fields = ["id", "nombre", "descripcion", "precio", "url_imagen", "categoria", "sucursal"]


class CrearOrdenSerializer(serializers.Serializer):
    mesa = serializers.IntegerField()
    cliente_nombre = serializers.CharField(max_length=150, required=False, allow_blank=True)
    cliente_telefono = serializers.CharField(max_length=30, required=False, allow_blank=True)


class AgregarProductoSerializer(serializers.Serializer):
    producto = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, max_value=50)


class AsignarMesaSerializer(serializers.Serializer):
    mesa = serializers.IntegerField()


class IniciarPreparacionSerializer(serializers.Serializer):
    tiempo_estimado = serializers.IntegerField(min_value=1, max_value=240)


class SucursalPublicaSerializer(serializers.ModelSerializer):
    restaurante = serializers.CharField(source="restaurante.nombre", read_only=True)
    distancia_km = serializers.FloatField(read_only=True, default=None)

    class Meta:
        model = Sucursal
        fields = ["id", "nombre", "restaurante", "direccion", "telefono", "latitud", "longitud", "distancia_km"]


class LineaPedidoSerializer(serializers.Serializer):
    producto = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1, max_value=MAX_CANTIDAD_POR_PRODUCTO)


class PedidoPublicoSerializer(serializers.Serializer):
    sucursal = serializers.IntegerField()
    tipo_consumo = serializers.ChoiceField(choices=Orden.TIPO_CONSUMO_CHOICES)
    nombre = serializers.CharField(max_length=150, required=False, allow_blank=True)
    lineas = LineaPedidoSerializer(many=True, allow_empty=False)


class PedidoPublicoRespuestaSerializer(serializers.Serializer):
    codigo = serializers.CharField()
    orden = OrdenSerializer()
