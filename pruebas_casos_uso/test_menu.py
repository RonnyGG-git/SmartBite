from decimal import Decimal

from django.urls import reverse

from catalogo.models import Producto
from operativo.models import Orden
from recetas.models import ProductoIngrediente

from .base import CasoDeUsoTestCase


class MenuTests(CasoDeUsoTestCase):

    def setUp(self):
        self.entrar_como("JEFE_COCINA")

    def datos_producto(self, **cambios):
        datos = {
            "nombre": "Limonada", "descripcion": "", "precio": "6000", "url_imagen": "",
            "categoria": self.bebidas.pk, "sucursal": self.sucursal.pk, "disponible": "on",
        }
        datos.update(cambios)
        return datos

    def menu_del_cliente(self):
        self.escanear_qr()
        respuesta = self.client.get(reverse("cliente:menu"))
        return respuesta, [p for _, lista in respuesta.context["categorias"] for p in lista]

    def test_cu_men_01_gestionar_catalogo_de_platillos(self):
        self.assertTrue(self.client.get(reverse("catalogo:productos_list")).context["puede_gestionar"])
        self.entrar_como("JEFE_INVENTARIO")
        self.assertFalse(self.client.get(reverse("catalogo:productos_list")).context["puede_gestionar"])
        self.entrar_como("MESERO")
        self.assertEqual(self.client.get(reverse("catalogo:productos_list")).status_code, 403)

    def test_cu_men_02_agregar_platillo(self):
        self.client.post(reverse("catalogo:producto_crear"), self.datos_producto())
        self.assertTrue(Producto.objects.filter(nombre="Limonada").exists())

    def test_cu_men_03_definir_receta_e_insumos(self):
        url = reverse("recetas:receta_crear")
        datos = {"producto": self.gaseosa.pk, "item_inventario": self.pan.pk, "unidad_medida": "", "activo": "on"}
        self.client.post(url, {**datos, "cantidad_requerida": "0"})
        self.assertFalse(self.gaseosa.ingredientes.exists())
        self.client.post(url, {**datos, "cantidad_requerida": "0.5"})
        self.assertEqual(self.gaseosa.ingredientes.get().cantidad_requerida, Decimal("0.5"))

    def test_cu_men_04_actualizar_platillo(self):
        self.client.post(
            reverse("catalogo:producto_editar", args=[self.gaseosa.pk]), self.datos_producto(nombre="Gaseosa 400 ml")
        )
        self.gaseosa.refresh_from_db()
        self.assertEqual(self.gaseosa.nombre, "Gaseosa 400 ml")

    def test_cu_men_05_eliminar_platillo(self):
        self.client.post(reverse("catalogo:producto_eliminar", args=[self.gaseosa.pk]))
        self.assertFalse(Producto.objects.filter(pk=self.gaseosa.pk).exists())

    def test_cu_men_06_actualizar_menu(self):
        self.client.post(reverse("catalogo:producto_crear"), self.datos_producto())
        _, productos = self.menu_del_cliente()
        self.assertIn(Producto.objects.get(nombre="Limonada"), productos)

    def test_cu_men_07_definir_precio_de_platillo(self):
        anterior = self.crear_orden(items=[(self.gaseosa, 1)])
        self.client.post(
            reverse("catalogo:producto_editar", args=[self.gaseosa.pk]),
            self.datos_producto(nombre="Gaseosa", precio="5500"),
        )
        self.assertEqual(anterior.detalles.get().precio_unitario, Decimal("5000"))
        self.gaseosa.refresh_from_db()
        self.assertEqual(self.gaseosa.precio, Decimal("5500"))

    def test_cu_men_08_consultar_disponibilidad_de_platillo(self):
        self.client.post(reverse("catalogo:producto_toggle_disponibilidad", args=[self.gaseosa.pk]))
        self.gaseosa.refresh_from_db()
        self.assertFalse(self.gaseosa.disponible)

    def test_cu_men_09_consultar_platillo(self):
        productos = self.client.get(reverse("catalogo:productos_list")).context["object_list"]
        self.assertIn(self.hamburguesa, list(productos))

    def test_cu_men_10_enviar_disponibilidad_del_platillo(self):
        Producto.objects.filter(pk=self.gaseosa.pk).update(disponible=False)
        _, productos = self.menu_del_cliente()
        self.assertNotIn(self.gaseosa, productos)
        self.client.post(reverse("cliente:autopedido"), {f"cant_{self.gaseosa.pk}": 1})
        self.assertFalse(Orden.objects.exists())

    def test_cu_men_11_enviar_informacion_del_platillo(self):
        respuesta, _ = self.menu_del_cliente()
        self.assertContains(respuesta, "Hamburguesa")
        self.assertTrue(ProductoIngrediente.objects.filter(producto=self.hamburguesa).exists())
