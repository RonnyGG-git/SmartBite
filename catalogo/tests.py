from django.test import TestCase
from django.urls import reverse

from core.testing import crear_escenario, crear_usuario


class PermisosPlatillosTests(TestCase):
    """Platillos y categorías: los gestionan Administrador y Chef; el Jefe de
    Inventario solo los consulta."""

    def setUp(self):
        self.d = crear_escenario()
        self.producto = self.d["bandeja"]

    def test_chef_crea_y_edita_platillos(self):
        self.client.force_login(crear_usuario("JEFE_COCINA"))
        self.assertEqual(self.client.get(reverse("catalogo:producto_crear")).status_code, 200)
        self.assertEqual(self.client.get(reverse("catalogo:producto_editar", args=[self.producto.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("catalogo:categoria_crear")).status_code, 200)
        self.assertContains(self.client.get(reverse("catalogo:productos_list")), reverse("catalogo:producto_crear"))

    def test_chef_cambia_disponibilidad(self):
        self.client.force_login(crear_usuario("JEFE_COCINA"))
        self.client.post(reverse("catalogo:producto_toggle_disponibilidad", args=[self.producto.pk]))
        self.producto.refresh_from_db()
        self.assertFalse(self.producto.disponible)

    def test_jefe_inventario_solo_consulta(self):
        self.client.force_login(crear_usuario("JEFE_INVENTARIO"))
        resp = self.client.get(reverse("catalogo:productos_list"))
        self.assertContains(resp, "Bandeja paisa")
        self.assertNotContains(resp, reverse("catalogo:producto_crear"))
        self.assertEqual(self.client.get(reverse("catalogo:producto_crear")).status_code, 403)
        self.assertEqual(self.client.get(reverse("catalogo:categoria_crear")).status_code, 403)

        self.client.post(reverse("catalogo:producto_toggle_disponibilidad", args=[self.producto.pk]))
        self.producto.refresh_from_db()
        self.assertTrue(self.producto.disponible)
