from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from caja.models import MetodoPago
from catalogo.models import Categoria, Producto
from cuentas.models import ROLES_SISTEMA, Rol, Usuario
from inventario.models import ItemInventario
from operativo.models import DetalleOrden, Mesa, Orden
from recetas.models import ProductoIngrediente
from restaurantes.models import Restaurante, Sucursal

CLAVE = "Clave-Segura-2026!"


class CasoDeUsoTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.restaurante = Restaurante.objects.create(
            nombre="Smart Bite", nif="900123456-1", email="info@smartbite.co", direccion="Calle 1"
        )
        cls.sucursal = Sucursal.objects.create(restaurante=cls.restaurante, nombre="Centro")
        cls.otra_sucursal = Sucursal.objects.create(restaurante=cls.restaurante, nombre="Norte")
        cls.mesa = Mesa.objects.create(numero=1, sucursal=cls.sucursal)

        cls.bebidas = Categoria.objects.create(nombre="Bebidas", restaurante=cls.restaurante)
        cls.platos = Categoria.objects.create(nombre="Platos fuertes", restaurante=cls.restaurante)
        cls.gaseosa = Producto.objects.create(
            nombre="Gaseosa", precio=Decimal("5000"), categoria=cls.bebidas, sucursal=cls.sucursal
        )
        cls.hamburguesa = Producto.objects.create(
            nombre="Hamburguesa", precio=Decimal("20000"), categoria=cls.platos, sucursal=cls.sucursal
        )

        cls.pan = ItemInventario.objects.create(
            nombre="Pan", stock_actual=10, stock_minimo=2, sucursal=cls.sucursal
        )
        ProductoIngrediente.objects.create(
            producto=cls.hamburguesa, item_inventario=cls.pan, cantidad_requerida=Decimal("1")
        )

        cls.efectivo = MetodoPago.objects.create(nombre="Efectivo")
        cls.tarjeta = MetodoPago.objects.create(nombre="Tarjeta")

        cls.usuarios = {}
        for nombre_rol, _ in ROLES_SISTEMA:
            rol = Rol.objects.create(nombre=nombre_rol)
            cls.usuarios[nombre_rol] = Usuario.objects.create_user(
                email=f"{nombre_rol.lower()}@smartbite.co",
                nombre=nombre_rol.title(),
                password=CLAVE,
                rol=rol,
                sucursal=cls.sucursal,
                restaurante=cls.restaurante,
            )

    def entrar_como(self, nombre_rol):
        self.client.force_login(self.usuarios[nombre_rol])

    def crear_orden(self, estado=Orden.PENDIENTE, items=None, **campos):
        orden = Orden.objects.create(mesa=self.mesa, estado=estado, **campos)
        for producto, cantidad in items or [(self.gaseosa, 2)]:
            DetalleOrden.objects.create(
                orden=orden, producto=producto, cantidad=cantidad, precio_unitario=producto.precio
            )
        if estado not in (Orden.ENTREGADA, Orden.CANCELADA):
            Mesa.objects.filter(pk=self.mesa.pk).update(estado=Mesa.OCUPADA)
        return orden

    def escanear_qr(self, tipo="EN_RESTAURANTE"):
        respuesta = self.client.get(reverse("cliente:mesa", args=[self.mesa.pk]))
        if tipo:
            self.client.post(reverse("cliente:tipo_consumo"), {"tipo": tipo})
        return respuesta
