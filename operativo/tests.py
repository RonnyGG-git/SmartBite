from django.test import TestCase
from django.urls import reverse

from caja.models import MetodoPago
from core.testing import crear_escenario, crear_usuario
from operativo.models import DetalleOrden, Mesa, Orden


class FlujoPedidoTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.mesa = self.d["mesa"]
        self.mesa.estado = Mesa.OCUPADA
        self.mesa.save()
        self.orden = Orden.objects.create(mesa=self.mesa)
        DetalleOrden.objects.create(orden=self.orden, producto=self.d["bandeja"], cantidad=1, precio_unitario=32000)

    def cambiar_estado(self, estado):
        return self.client.post(reverse("operativo:cambiar_estado_orden", args=[self.orden.pk]), {"estado": estado})

    def test_sin_sesion_no_se_puede_cambiar_estado(self):
        self.cambiar_estado(Orden.CANCELADA)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_mesero_cancela_pendiente_y_libera_mesa(self):
        self.client.force_login(crear_usuario("MESERO"))
        self.cambiar_estado(Orden.CANCELADA)
        self.orden.refresh_from_db()
        self.mesa.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.CANCELADA)
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)

    def test_mesero_no_cierra_la_orden_sin_cobro(self):
        self.orden.estado = Orden.LISTA
        self.orden.save()
        self.client.force_login(crear_usuario("MESERO"))
        self.cambiar_estado(Orden.ENTREGADA)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.LISTA)

    def test_no_se_agregan_productos_con_la_orden_en_cocina(self):
        self.orden.estado = Orden.EN_PREPARACION
        self.orden.save()
        self.client.force_login(crear_usuario("MESERO"))
        self.client.post(reverse("operativo:agregar_producto", args=[self.orden.pk]), {"producto": self.d["bandeja"].pk, "cantidad": 1})
        self.assertEqual(self.orden.detalles.count(), 1)

    def test_solicitar_cuenta_llega_a_caja_y_el_cobro_cierra_la_orden(self):
        self.orden.estado = Orden.LISTA
        self.orden.save()
        self.client.force_login(crear_usuario("MESERO"))
        self.client.post(reverse("operativo:solicitar_cuenta", args=[self.orden.pk]))
        self.orden.refresh_from_db()
        self.assertIsNotNone(self.orden.cuenta_solicitada_en)

        self.client.force_login(crear_usuario("CAJERO"))
        self.assertContains(self.client.get(reverse("caja:por_cobrar")), f"#{self.orden.pk}")
        metodo = MetodoPago.objects.create(nombre="Efectivo")
        resp = self.client.post(reverse("caja:cobrar_orden", args=[self.orden.pk]), {"metodo_pago": metodo.pk, "monto": "32000"})
        self.assertRedirects(resp, reverse("caja:ventas_list"))
        self.orden.refresh_from_db()
        self.mesa.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.ENTREGADA)
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)

    def test_cobrar_sin_sesion_no_revienta(self):
        resp = self.client.get(reverse("caja:cobrar_orden", args=[self.orden.pk]))
        self.assertEqual(resp.status_code, 302)

    def test_qr_de_mesa_apunta_al_modulo_cliente(self):
        self.client.force_login(crear_usuario("MESERO"))
        resp = self.client.get(reverse("operativo:generar_qr", args=[self.mesa.pk]))
        self.assertContains(resp, reverse("cliente:mesa", args=[self.mesa.pk]))
