from django.test import TestCase
from django.urls import reverse

from core.testing import crear_escenario, crear_usuario
from inventario.models import ItemInventario


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
