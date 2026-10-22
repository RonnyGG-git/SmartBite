from django.urls import reverse

from cliente.views import SESION_CARRITO, SESION_TIPO_CONSUMO
from operativo.models import Mesa, Orden

from .base import CasoDeUsoTestCase


class FlujoClienteTests(CasoDeUsoTestCase):

    def elegir(self, tipo):
        return self.client.post(reverse("cliente:tipo_consumo"), {"tipo": tipo})

    def al_carrito(self, *pares, nombre=""):
        datos = {f"cant_{p.pk}": c for p, c in pares}
        datos["nombre"] = nombre
        return self.client.post(reverse("cliente:carrito"), datos)

    def test_cu_ped_16_el_qr_asigna_la_mesa_y_pide_el_tipo_de_consumo(self):
        respuesta = self.escanear_qr(tipo=None)
        self.assertRedirects(respuesta, reverse("cliente:tipo_consumo"))
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.OCUPADA)

    def test_cu_ped_16_mesa_ocupada_por_otro_solo_ve_el_menu(self):
        self.escanear_qr()
        self.client.logout()
        self.assertRedirects(self.escanear_qr(tipo=None), reverse("cliente:menu"))
        self.assertFalse(self.client.get(reverse("cliente:menu")).context["puede_pedir"])

    def test_cu_ped_24_elegir_tipo_de_consumo(self):
        self.escanear_qr(tipo=None)
        self.assertRedirects(self.elegir(Orden.PARA_LLEVAR), reverse("cliente:menu"))
        self.assertEqual(self.client.session[SESION_TIPO_CONSUMO], Orden.PARA_LLEVAR)
        self.elegir("OTRA_COSA")
        self.assertEqual(self.client.session[SESION_TIPO_CONSUMO], Orden.PARA_LLEVAR)

    def test_cu_ped_24_sin_tipo_no_se_ve_el_menu_para_pedir(self):
        self.escanear_qr(tipo=None)
        self.assertRedirects(self.client.get(reverse("cliente:menu")), reverse("cliente:tipo_consumo"))

    def test_cu_ped_01_el_menu_completo_es_igual_para_los_dos_tipos(self):
        menus = []
        for tipo in (Orden.EN_RESTAURANTE, Orden.PARA_LLEVAR):
            self.escanear_qr(tipo=tipo)
            contexto = self.client.get(reverse("cliente:menu")).context
            menus.append([(c, list(ps)) for c, ps in contexto["categorias"]])
        self.assertEqual(menus[0], menus[1])
        self.assertEqual([c for c, _ in menus[0]], [self.bebidas, self.platos])

    def test_cu_ped_05_ir_al_apartado_de_compra(self):
        self.escanear_qr()
        respuesta = self.al_carrito((self.gaseosa, 2), (self.hamburguesa, 1), nombre="Ana")
        self.assertRedirects(respuesta, reverse("cliente:compra"))
        compra = self.client.get(reverse("cliente:compra"))
        self.assertEqual(compra.context["total"], 30000)
        self.assertEqual(self.client.session[SESION_CARRITO], {str(self.gaseosa.pk): 2, str(self.hamburguesa.pk): 1})
        self.assertFalse(Orden.objects.exists())

    def test_cu_ped_05_carrito_vacio_no_pasa_a_la_compra(self):
        self.escanear_qr()
        self.assertRedirects(self.al_carrito(), reverse("cliente:menu"))
        self.assertRedirects(self.client.get(reverse("cliente:compra")), reverse("cliente:menu"))

    def test_cu_ped_05_volver_al_menu_conserva_el_carrito(self):
        self.escanear_qr()
        self.al_carrito((self.gaseosa, 3))
        productos = [p for _, ps in self.client.get(reverse("cliente:menu")).context["categorias"] for p in ps]
        self.assertEqual({p: p.cantidad_carrito for p in productos}, {self.gaseosa: 3, self.hamburguesa: 0})

    def test_confirmar_la_compra_registra_el_pedido_con_su_tipo(self):
        self.escanear_qr(tipo=Orden.PARA_LLEVAR)
        self.al_carrito((self.hamburguesa, 1))
        datos = {f"cant_{self.hamburguesa.pk}": 1, "nombre": ""}
        self.client.post(reverse("cliente:autopedido"), datos)
        orden = Orden.objects.get()
        self.assertEqual((orden.tipo_consumo, orden.estado), (Orden.PARA_LLEVAR, Orden.PENDIENTE))
        self.assertNotIn(SESION_CARRITO, self.client.session)
        self.entrar_como("JEFE_COCINA")
        self.assertContains(self.client.get(reverse("cocina:cocina")), "PARA LLEVAR")
