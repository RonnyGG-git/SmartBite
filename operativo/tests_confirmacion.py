from django.test import TestCase
from django.urls import reverse

from core.testing import crear_escenario, crear_usuario
from operativo.models import Mesa, Orden
from restaurantes.models import Restaurante


class ConfirmacionMeseroTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.mesero = crear_usuario("MESERO")

    def pedir_desde_mesa(self, tipo="EN_RESTAURANTE"):
        self.client.get(reverse("cliente:mesa", args=[self.d["mesa"].pk]))
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": tipo})
        self.client.post(reverse("cliente:autopedido"), {f"cant_{self.d['bandeja'].pk}": 2})
        return Orden.objects.get()

    def test_pedido_por_qr_espera_al_mesero_y_no_llega_a_cocina(self):
        orden = self.pedir_desde_mesa()
        self.assertEqual(orden.estado, Orden.POR_CONFIRMAR)
        self.assertTrue(orden.requiere_confirmacion)
        self.assertFalse(orden.cobrable)
        self.client.force_login(crear_usuario("JEFE_COCINA"))
        self.assertNotContains(self.client.get(reverse("cocina:cocina")), f"#{orden.pk} ·")

    def test_para_llevar_tambien_espera_al_mesero(self):
        self.assertTrue(self.pedir_desde_mesa("PARA_LLEVAR").requiere_confirmacion)

    def test_cliente_ve_el_numero_para_mostrarlo(self):
        orden = self.pedir_desde_mesa()
        respuesta = self.client.get(reverse("cliente:pedido", args=[orden.pk]))
        self.assertContains(respuesta, "Muéstrale este número a tu mesero")
        self.assertContains(respuesta, 'content="8"')

    def test_alerta_llega_al_mesero(self):
        orden = self.pedir_desde_mesa()
        self.client.force_login(self.mesero)
        pedidos = self.client.get(reverse("operativo:alertas_confirmacion")).json()["pedidos"]
        self.assertEqual([p["id"] for p in pedidos], [orden.pk])
        self.assertEqual(pedidos[0]["lugar"], f"Mesa {self.d['mesa'].numero}")
        self.assertEqual(pedidos[0]["platillos"], ["2 × Bandeja paisa"])

    def test_mesero_de_otro_restaurante_no_ve_la_alerta(self):
        self.pedir_desde_mesa()
        otro = Restaurante.objects.create(nombre="Otro", nif="900999999", email="o@o.co", direccion="Calle 1")
        self.client.force_login(crear_usuario("MESERO", email="otro@test.co", restaurante=otro))
        self.assertEqual(self.client.get(reverse("operativo:alertas_confirmacion")).json()["pedidos"], [])

    def test_confirmar_envia_a_cocina(self):
        orden = self.pedir_desde_mesa()
        self.client.force_login(self.mesero)
        self.client.post(reverse("operativo:confirmar_pedido", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.PENDIENTE)

    def test_rechazar_cancela_y_libera_la_mesa(self):
        orden = self.pedir_desde_mesa()
        self.client.force_login(self.mesero)
        self.client.post(reverse("operativo:rechazar_pedido", args=[orden.pk]))
        orden.refresh_from_db()
        self.d["mesa"].refresh_from_db()
        self.assertEqual(orden.estado, Orden.CANCELADA)
        self.assertEqual(self.d["mesa"].estado, Mesa.DISPONIBLE)

    def test_no_se_confirma_dos_veces(self):
        orden = self.pedir_desde_mesa()
        self.client.force_login(self.mesero)
        url = reverse("operativo:confirmar_pedido", args=[orden.pk])
        self.client.post(url)
        respuesta = self.client.post(url, headers={"X-Requested-With": "XMLHttpRequest"})
        self.assertEqual(respuesta.status_code, 409)

    def test_cajero_no_puede_confirmar_como_mesero(self):
        orden = self.pedir_desde_mesa()
        self.client.force_login(crear_usuario("CAJERO"))
        self.client.post(reverse("operativo:confirmar_pedido", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.POR_CONFIRMAR)

    def test_pedido_del_mesero_no_pide_confirmacion(self):
        orden = Orden.objects.create(mesa=self.d["mesa"], estado=Orden.POR_CONFIRMAR, origen=Orden.ORIGEN_TELEFONO)
        self.assertFalse(orden.requiere_confirmacion)

    def test_tipo_ofrece_reservar_mesa(self):
        self.client.get(reverse("cliente:mesa", args=[self.d["mesa"].pk]))
        respuesta = self.client.get(reverse("cliente:tipo_consumo"))
        self.assertContains(respuesta, "Comer en el restaurante")
        self.assertContains(respuesta, "Para llevar")
        self.assertContains(respuesta, reverse("cliente:reservar"))
