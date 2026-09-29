from django.test import TestCase
from django.urls import reverse

from core.testing import crear_escenario, crear_usuario
from operativo.models import Mesa, Orden

from .models import Retroalimentacion


class MenuClienteTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()

    def escanear(self, mesa=None):
        return self.client.get(reverse("cliente:mesa", args=[(mesa or self.d["mesa"]).pk]))

    def test_qr_identifica_la_mesa_y_lleva_al_menu(self):
        resp = self.escanear()
        self.assertRedirects(resp, reverse("cliente:menu"))
        self.assertEqual(self.client.session["cliente_mesa_id"], self.d["mesa"].pk)

    def test_menu_solo_muestra_platillos_de_la_sucursal_de_la_mesa(self):
        self.escanear()
        resp = self.client.get(reverse("cliente:menu"))
        self.assertContains(resp, "Bandeja paisa")
        self.assertNotContains(resp, "Ajiaco")  # es de la sucursal Norte

    def test_menu_se_ve_igual_con_sesion_de_personal_abierta(self):
        self.client.force_login(crear_usuario("MESERO"))
        self.escanear()
        resp = self.client.get(reverse("cliente:menu"))
        self.assertContains(resp, "Bandeja paisa")
        self.assertNotContains(resp, 'class="sidebar"')

    def test_qr_antiguo_redirige_al_modulo_cliente(self):
        resp = self.client.get(reverse("menu_cliente:menu") + f"?mesa={self.d['mesa'].pk}")
        self.assertRedirects(resp, reverse("cliente:mesa", args=[self.d["mesa"].pk]), fetch_redirect_response=False)

    def test_mesa_inactiva_da_404(self):
        mesa = Mesa.objects.create(numero=9, sucursal=self.d["centro"], activa=False)
        self.assertEqual(self.escanear(mesa).status_code, 404)


class AutopedidoTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.client.get(reverse("cliente:mesa", args=[self.d["mesa"].pk]))

    def pedir(self, **cantidades):
        datos = {f"cant_{self.d[k].pk}": v for k, v in cantidades.items()}
        return self.client.post(reverse("cliente:autopedido"), datos)

    def test_autopedido_crea_orden_en_cola_de_cocina_y_ocupa_la_mesa(self):
        resp = self.pedir(bandeja=2)
        orden = Orden.objects.get()
        self.assertRedirects(resp, reverse("cliente:pedido", args=[orden.pk]))
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.assertEqual(orden.origen, Orden.ORIGEN_AUTOPEDIDO)
        self.assertEqual(orden.total, 64000)
        self.d["mesa"].refresh_from_db()
        self.assertEqual(self.d["mesa"].estado, Mesa.OCUPADA)

    def test_ignora_platillos_de_otra_sucursal(self):
        self.pedir(bandeja=1, ajiaco=3)
        detalles = Orden.objects.get().detalles.all()
        self.assertEqual([d.producto.nombre for d in detalles], ["Bandeja paisa"])

    def test_sin_platillos_no_crea_orden(self):
        self.pedir(bandeja=0)
        self.assertFalse(Orden.objects.exists())

    def test_cantidad_se_limita_al_maximo(self):
        self.pedir(bandeja=500)
        self.assertEqual(Orden.objects.get().detalles.get().cantidad, 20)

    def test_mesa_ocupada_no_acepta_otro_autopedido(self):
        self.pedir(bandeja=1)
        otro = self.client_class()
        otro.get(reverse("cliente:mesa", args=[self.d["mesa"].pk]))
        otro.post(reverse("cliente:autopedido"), {f"cant_{self.d['bandeja'].pk}": 1})
        self.assertEqual(Orden.objects.count(), 1)

    def test_estado_del_pedido_solo_para_quien_lo_hizo(self):
        self.pedir(bandeja=1)
        orden = Orden.objects.get()
        self.assertContains(self.client.get(reverse("cliente:pedido", args=[orden.pk])), "Recibido en cocina")
        extraño = self.client_class()
        self.assertEqual(extraño.get(reverse("cliente:pedido", args=[orden.pk])).status_code, 404)

    def test_sin_mesa_escaneada_no_se_puede_pedir(self):
        anonimo = self.client_class()
        anonimo.post(reverse("cliente:autopedido"), {f"cant_{self.d['bandeja'].pk}": 1})
        self.assertFalse(Orden.objects.exists())


class RetroalimentacionTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()

    def test_cliente_envia_denuncia_asociada_a_su_mesa(self):
        self.client.get(reverse("cliente:mesa", args=[self.d["mesa"].pk]))
        self.client.post(reverse("cliente:retroalimentacion"), {"tipo": "DENUNCIA", "mensaje": "La sopa llegó fría"})
        item = Retroalimentacion.objects.get()
        self.assertEqual(item.tipo, Retroalimentacion.DENUNCIA)
        self.assertEqual(item.mesa, self.d["mesa"])

    def test_solo_el_administrador_revisa_los_mensajes(self):
        item = Retroalimentacion.objects.create(mensaje="Más opciones veganas")
        self.client.force_login(crear_usuario("MESERO"))
        self.assertEqual(self.client.get(reverse("cliente:retroalimentacion_list")).status_code, 403)

        self.client.force_login(crear_usuario("ADMINISTRADOR"))
        self.assertContains(self.client.get(reverse("cliente:retroalimentacion_list")), "Más opciones veganas")
        self.client.post(reverse("cliente:retroalimentacion_revisar", args=[item.pk]))
        item.refresh_from_db()
        self.assertTrue(item.revisada)
