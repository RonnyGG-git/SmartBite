from rest_framework import serializers

from catalogo.models import Categoria, Producto
from cliente.models import Retroalimentacion
from cuentas.models import Rol, Usuario
from inventario.models import Compra, DetalleCompra, ItemInventario, MovimientoInventario, Proveedor
from operativo.models import Mesa, Reserva
from recetas.models import ProductoIngrediente
from restaurantes.models import Restaurante, Sucursal


class ItemSerializer(serializers.ModelSerializer):
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    stock_bajo = serializers.BooleanField(read_only=True)

    class Meta:
        model = ItemInventario
        fields = [
            "id", "nombre", "descripcion", "unidad_medida", "stock_actual", "stock_minimo", "costo_unitario",
            "ubicacion", "sucursal", "sucursal_nombre", "stock_bajo",
        ]


class MovimientoSerializer(serializers.ModelSerializer):
    item_nombre = serializers.CharField(source="item.nombre", read_only=True)
    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)

    class Meta:
        model = MovimientoInventario
        fields = ["id", "item", "item_nombre", "tipo", "tipo_nombre", "cantidad", "motivo", "creado_en"]


class ProveedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proveedor
        fields = ["id", "nombre", "contacto", "telefono", "email", "direccion", "activo"]


class DetalleCompraSerializer(serializers.ModelSerializer):
    item_nombre = serializers.CharField(source="item.nombre", read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = DetalleCompra
        fields = ["id", "item", "item_nombre", "cantidad", "costo_unitario", "subtotal"]


class CompraSerializer(serializers.ModelSerializer):
    proveedor_nombre = serializers.CharField(source="proveedor.nombre", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    detalles = DetalleCompraSerializer(many=True, read_only=True)

    class Meta:
        model = Compra
        fields = ["id", "proveedor", "proveedor_nombre", "estado", "estado_nombre", "total", "creado_en", "detalles"]


class LineaCompraSerializer(serializers.Serializer):
    item = serializers.IntegerField()
    cantidad = serializers.IntegerField(min_value=1)
    costo_unitario = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class NuevaCompraSerializer(serializers.Serializer):
    proveedor = serializers.IntegerField()
    detalles = LineaCompraSerializer(many=True, allow_empty=False)


class RecetaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    item_nombre = serializers.CharField(source="item_inventario.nombre", read_only=True)

    class Meta:
        model = ProductoIngrediente
        fields = ["id", "producto", "producto_nombre", "item_inventario", "item_nombre", "cantidad_requerida", "unidad_medida", "activo"]


class CategoriaGestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nombre"]


class ProductoGestionSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    imagen = serializers.SerializerMethodField()

    class Meta:
        model = Producto
        fields = [
            "id", "nombre", "descripcion", "precio", "url_imagen", "categoria", "categoria_nombre",
            "sucursal", "sucursal_nombre", "disponible", "imagen",
        ]

    def get_imagen(self, producto) -> str:
        request = self.context.get("request")
        fuente = producto.imagen_src
        return request.build_absolute_uri(fuente) if request and fuente and fuente.startswith("/") else fuente


class MesaGestionSerializer(serializers.ModelSerializer):
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = Mesa
        fields = ["id", "numero", "capacidad", "sucursal", "sucursal_nombre", "activa", "estado", "estado_nombre"]


class SucursalGestionSerializer(serializers.ModelSerializer):
    restaurante_nombre = serializers.CharField(source="restaurante.nombre", read_only=True)

    class Meta:
        model = Sucursal
        fields = ["id", "restaurante", "restaurante_nombre", "nombre", "direccion", "telefono", "latitud", "longitud", "activo"]


class RestauranteGestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restaurante
        fields = [
            "id", "nombre", "nif", "email", "direccion", "telefono", "telefono_secundario", "logo_url", "activo",
            "codigo_acceso",
        ]


class UsuarioGestionSerializer(serializers.ModelSerializer):
    rol_nombre = serializers.CharField(source="rol.get_nombre_display", default=None, read_only=True)
    sucursal_nombre = serializers.CharField(source="sucursal.nombre", default=None, read_only=True)

    class Meta:
        model = Usuario
        fields = ["id", "nombre", "email", "rol", "rol_nombre", "sucursal", "sucursal_nombre", "is_active"]


class RolSerializer(serializers.ModelSerializer):
    etiqueta = serializers.CharField(source="get_nombre_display", read_only=True)

    class Meta:
        model = Rol
        fields = ["id", "nombre", "etiqueta"]


class OpinionSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)
    mesa_numero = serializers.IntegerField(source="mesa.numero", default=None, read_only=True)

    class Meta:
        model = Retroalimentacion
        fields = ["id", "tipo", "tipo_nombre", "mensaje", "nombre", "contacto", "mesa", "mesa_numero", "revisada", "creado_en"]


class ReservaPublicaSerializer(serializers.ModelSerializer):
    mesa_numero = serializers.IntegerField(source="mesa.numero", read_only=True)
    sucursal = serializers.CharField(source="mesa.sucursal.nombre", read_only=True)
    restaurante = serializers.CharField(source="mesa.sucursal.restaurante.nombre", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)

    class Meta:
        model = Reserva
        fields = [
            "id", "codigo", "mesa_numero", "sucursal", "restaurante", "fecha_hora", "num_personas", "nombre",
            "telefono", "estado", "estado_nombre",
        ]
