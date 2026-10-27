from django.test import TestCase
from django.urls import reverse

from core.testing import crear_escenario, crear_usuario
from inventario.models import ItemInventario, MovimientoInventario


class PermisosInventarioTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        ItemInventario.objects.create(nombre="Arroz", stock_actual=10, sucursal=self.d["centro"])

    def test_jefe_cocina_ve_inventario_sin_acciones_de_escritura(self):
        self.client.force_login(crear_usuario("JEFE_COCINA"))
        resp = self.client.get(reverse("inventario:inventario_list"))
        self.assertContains(resp, "Arroz")
        self.assertNotContains(resp, reverse("inventario:item_crear"))
        self.assertNotContains(resp, "Ajustar")

    def test_jefe_inventario_ve_acciones(self):
        self.client.force_login(crear_usuario("JEFE_INVENTARIO"))
        resp = self.client.get(reverse("inventario:inventario_list"))
        self.assertContains(resp, reverse("inventario:item_crear"))

    def test_ajuste_sin_sesion_no_revienta(self):
        item = ItemInventario.objects.get()
        self.assertEqual(self.client.get(reverse("inventario:item_ajustar", args=[item.pk])).status_code, 302)


class AjustarStockTests(TestCase):
    """ItemInventario.ajustar_stock(): la regla única que usan la vista web y la API."""

    def setUp(self):
        d = crear_escenario()
        self.item = ItemInventario.objects.create(nombre="Leche", stock_actual=10, stock_minimo=5, sucursal=d["centro"])

    def test_entrada_suma_y_crea_el_movimiento(self):
        mov = self.item.ajustar_stock(MovimientoInventario.ENTRADA, 4, "Compra al por menor")
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 14)
        self.assertEqual((mov.tipo, mov.cantidad, mov.motivo, mov.item_id),
                         ("ENTRADA", 4, "Compra al por menor", self.item.pk))

    def test_salida_resta(self):
        self.item.ajustar_stock(MovimientoInventario.SALIDA, 7, "Consumo de cocina")
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 3)

    def test_salida_mayor_que_el_stock_lo_deja_en_cero(self):
        mov = self.item.ajustar_stock(MovimientoInventario.SALIDA, 15, "Pérdida")
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 0)
        self.assertEqual(mov.cantidad, 15)

    def test_actualiza_la_instancia_en_memoria(self):
        self.item.ajustar_stock(MovimientoInventario.ENTRADA, 1, "x")
        self.assertEqual(self.item.stock_actual, 11)

    def test_tipo_invalido_no_cambia_nada(self):
        with self.assertRaises(ValueError):
            self.item.ajustar_stock("AJUSTE", 1, "x")
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_cantidad_menor_que_uno_no_cambia_nada(self):
        with self.assertRaises(ValueError):
            self.item.ajustar_stock(MovimientoInventario.ENTRADA, 0, "x")
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_la_vista_web_sigue_ajustando(self):
        self.client.force_login(crear_usuario("JEFE_INVENTARIO"))
        resp = self.client.post(reverse("inventario:item_ajustar", args=[self.item.pk]),
                                {"tipo": "SALIDA", "cantidad": 7, "motivo": "Consumo"})
        self.assertRedirects(resp, reverse("inventario:inventario_list"), fetch_redirect_response=False)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 3)
        self.assertEqual(MovimientoInventario.objects.get().cantidad, 7)

    def test_la_vista_web_no_deja_ajustar_al_jefe_de_cocina(self):
        self.client.force_login(crear_usuario("JEFE_COCINA"))
        self.client.post(reverse("inventario:item_ajustar", args=[self.item.pk]),
                         {"tipo": "SALIDA", "cantidad": 7, "motivo": "Consumo"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)
