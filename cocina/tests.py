from django.test import TestCase
from django.urls import reverse

from core.testing import crear_escenario, crear_usuario
from inventario.models import ItemInventario
from operativo.models import DetalleOrden, Orden
from recetas.models import ProductoIngrediente


class CocinaTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.orden = Orden.objects.create(mesa=self.d["mesa"])
        DetalleOrden.objects.create(orden=self.orden, producto=self.d["bandeja"], cantidad=2, precio_unitario=32000)
        self.client.force_login(crear_usuario("JEFE_COCINA"))

    def accion(self, accion, **extra):
        return self.client.post(reverse("cocina:actualizar_estado", args=[self.orden.pk]), {"accion": accion, **extra})

    def test_chef_inicia_con_tiempo_estimado_y_marca_listo(self):
        self.accion("iniciar", tiempo_estimado=20)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.EN_PREPARACION)
        self.assertEqual(self.orden.tiempo_estimado_min, 20)
        self.assertIsNotNone(self.orden.listo_estimado_en)

        self.accion("listo")
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.LISTA)

    def test_no_inicia_sin_tiempo_estimado_valido(self):
        self.accion("iniciar", tiempo_estimado="abc")
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_no_puede_saltarse_la_preparacion(self):
        self.accion("listo")
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_mesero_no_actualiza_estado_de_preparacion(self):
        self.client.force_login(crear_usuario("MESERO"))
        self.accion("iniciar", tiempo_estimado=10)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_ticket_avisa_insumo_insuficiente(self):
        chorizo = ItemInventario.objects.create(nombre="Chorizo", stock_actual=1, sucursal=self.d["centro"])
        ProductoIngrediente.objects.create(producto=self.d["bandeja"], item_inventario=chorizo, cantidad_requerida=1)
        resp = self.client.get(reverse("cocina:cocina"))
        self.assertContains(resp, "Stock insuficiente: Chorizo")  # pide 2, hay 1
