from decimal import Decimal

from django.urls import reverse

from catalogo.models import Producto
from cliente.views import SESION_CARRITO, SESION_MESA, SESION_SUCURSAL
from operativo.models import Mesa, Orden
from restaurantes.forms import SucursalForm
from restaurantes.geo import distancia_km
from restaurantes.models import Restaurante, Sucursal

from .base import CasoDeUsoTestCase


class DirectorioTests(CasoDeUsoTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sucursal.latitud, cls.sucursal.longitud = Decimal("6.244203"), Decimal("-75.581211")
        cls.sucursal.save()
        cls.otro = Restaurante.objects.create(nombre="Arepas Doña Rosa", nif="901999888-2", email="r@r.co", direccion="Calle 2")
        cls.bogota = Sucursal.objects.create(
            restaurante=cls.otro, nombre="Chapinero", direccion="Cra 13 # 60-20",
            latitud=Decimal("4.648283"), longitud=Decimal("-74.063644"),
        )
        Producto.objects.create(nombre="Arepa de choclo", precio=Decimal("8000"), categoria=cls.platos, sucursal=cls.bogota)
        cls.cerrado = Restaurante.objects.create(nombre="Cerrado", nif="901777666-3", email="c@c.co", direccion="x", activo=False)
        sucursal_cerrada = Sucursal.objects.create(restaurante=cls.cerrado, nombre="Única")
        Producto.objects.create(nombre="Sopa", precio=Decimal("9000"), categoria=cls.platos, sucursal=sucursal_cerrada)

    def elegir_sucursal(self, sucursal, tipo=Orden.PARA_LLEVAR):
        respuesta = self.client.get(reverse("cliente:sucursal", args=[sucursal.pk]))
        if tipo:
            self.client.post(reverse("cliente:tipo_consumo"), {"tipo": tipo})
        return respuesta

    def pedir(self, *pares, nombre="Laura"):
        datos = {f"cant_{p.pk}": c for p, c in pares}
        datos["nombre"] = nombre
        self.client.post(reverse("cliente:carrito"), datos)
        return self.client.post(reverse("cliente:autopedido"), datos)

    def test_cu_ped_26_directorio_muestra_restaurantes_activos_con_menu(self):
        respuesta = self.client.get(reverse("cliente:restaurantes"))
        sucursales = list(respuesta.context["sucursales"])
        self.assertIn(self.sucursal, sucursales)
        self.assertIn(self.bogota, sucursales)
        self.assertNotIn(self.otra_sucursal, sucursales)
        self.assertNotContains(respuesta, "Cerrado")

    def test_cu_ped_25_ordena_por_cercania(self):
        respuesta = self.client.get(reverse("cliente:restaurantes"), {"lat": "4.65", "lng": "-74.06"})
        sucursales = respuesta.context["sucursales"]
        self.assertEqual(sucursales[0], self.bogota)
        self.assertLess(sucursales[0].distancia_km, 1)
        self.assertGreater(sucursales[1].distancia_km, 200)
        self.assertTrue(respuesta.context["con_ubicacion"])

    def test_cu_ped_25_ubicacion_invalida_se_ignora(self):
        respuesta = self.client.get(reverse("cliente:restaurantes"), {"lat": "999", "lng": "abc"})
        self.assertFalse(respuesta.context["con_ubicacion"])
        self.assertTrue(all(s.distancia_km is None for s in respuesta.context["sucursales"]))

    def test_cu_ped_26_buscar_por_nombre(self):
        respuesta = self.client.get(reverse("cliente:restaurantes"), {"q": "arepas"})
        self.assertEqual(list(respuesta.context["sucursales"]), [self.bogota])

    def test_cu_ped_26_elegir_restaurante_pide_tipo_de_consumo(self):
        respuesta = self.elegir_sucursal(self.bogota, tipo=None)
        self.assertRedirects(respuesta, reverse("cliente:tipo_consumo"))
        self.assertEqual(self.client.session[SESION_SUCURSAL], self.bogota.pk)
        menu = self.client.get(reverse("cliente:tipo_consumo"))
        self.assertContains(menu, "Chapinero")

    def test_cu_ped_26_restaurante_sin_menu_no_se_puede_elegir(self):
        self.assertEqual(self.client.get(reverse("cliente:sucursal", args=[self.otra_sucursal.pk])).status_code, 404)

    def test_cu_ped_05_pedido_desde_el_directorio_queda_sin_mesa(self):
        self.elegir_sucursal(self.sucursal)
        menu = self.client.get(reverse("cliente:menu"))
        self.assertTrue(menu.context["puede_pedir"])
        self.assertContains(menu, "Hamburguesa")
        respuesta = self.pedir((self.hamburguesa, 2), (self.gaseosa, 1))
        orden = Orden.objects.get()
        self.assertRedirects(respuesta, reverse("cliente:pedido", args=[orden.pk]))
        self.assertIsNone(orden.mesa)
        self.assertEqual(orden.sucursal, self.sucursal)
        self.assertEqual(orden.origen, Orden.ORIGEN_AUTOPEDIDO)
        self.assertEqual(orden.tipo_consumo, Orden.PARA_LLEVAR)
        self.assertEqual(orden.total, Decimal("45000"))
        self.assertEqual(orden.cliente.nombre, "Laura")
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)
        self.assertNotIn(SESION_CARRITO, self.client.session)
        self.assertEqual(orden.estado, Orden.POR_CONFIRMAR)
        self.assertContains(self.client.get(reverse("cliente:pedido", args=[orden.pk])), "Esperando confirmación")
        Orden.objects.filter(pk=orden.pk).update(estado=Orden.LISTA)
        self.assertContains(self.client.get(reverse("cliente:pedido", args=[orden.pk])), "pasar a recogerlo")

    def test_cu_ped_05_el_directorio_permite_varios_pedidos(self):
        self.elegir_sucursal(self.sucursal)
        self.pedir((self.gaseosa, 1))
        self.pedir((self.gaseosa, 3))
        self.assertEqual(Orden.objects.filter(mesa__isnull=True).count(), 2)
        self.assertEqual(Orden.objects.values("cliente").distinct().count(), 1)

    def test_cu_ped_05_no_acepta_productos_de_otra_sucursal(self):
        arepa = Producto.objects.get(nombre="Arepa de choclo")
        self.elegir_sucursal(self.sucursal)
        self.pedir((arepa, 1))
        self.assertFalse(Orden.objects.exists())

    def test_cu_ped_16_el_qr_lleva_directo_al_restaurante_de_la_mesa(self):
        self.elegir_sucursal(self.bogota)
        self.escanear_qr()
        self.assertEqual(self.client.session[SESION_SUCURSAL], self.sucursal.pk)
        self.assertEqual(self.client.session[SESION_MESA], self.mesa.pk)
        menu = self.client.get(reverse("cliente:menu"))
        self.assertEqual(menu.context["mesa"], self.mesa)
        self.assertContains(menu, "Hamburguesa")
        self.assertNotContains(menu, "Arepa de choclo")

    def test_elegir_restaurante_despues_del_qr_sale_de_la_mesa(self):
        self.escanear_qr()
        self.elegir_sucursal(self.bogota)
        self.assertNotIn(SESION_MESA, self.client.session)
        self.assertIsNone(self.client.get(reverse("cliente:menu")).context["mesa"])

    def test_sin_contexto_el_menu_invita_al_directorio(self):
        respuesta = self.client.get(reverse("cliente:menu"))
        self.assertContains(respuesta, reverse("cliente:restaurantes"))
        self.assertRedirects(self.client.post(reverse("cliente:autopedido"), {}), reverse("cliente:restaurantes"))


class AsignarMesaTests(CasoDeUsoTestCase):
    def crear_sin_mesa(self, tipo=Orden.EN_RESTAURANTE):
        orden = Orden.objects.create(sucursal=self.sucursal, origen=Orden.ORIGEN_AUTOPEDIDO, tipo_consumo=tipo)
        orden.detalles.create(producto=self.gaseosa, cantidad=1, precio_unitario=self.gaseosa.precio)
        return orden

    def test_cu_ped_04_mesero_ve_y_asigna_mesa_a_pedido_sin_mesa(self):
        orden = self.crear_sin_mesa()
        self.entrar_como("MESERO")
        self.assertContains(self.client.get(reverse("operativo:mesas_list")), f"#{orden.pk}")
        self.assertContains(self.client.get(reverse("operativo:detalle_orden", args=[orden.pk])), "asígnale una mesa")
        self.client.post(reverse("operativo:asignar_mesa", args=[orden.pk]), {"mesa": self.mesa.pk})
        orden.refresh_from_db()
        self.mesa.refresh_from_db()
        self.assertEqual(orden.mesa, self.mesa)
        self.assertEqual(self.mesa.estado, Mesa.OCUPADA)

    def test_cu_ped_04_no_asigna_mesa_ocupada_ni_de_otra_sucursal(self):
        ocupante = self.crear_orden()
        orden = self.crear_sin_mesa()
        otra = Mesa.objects.create(numero=9, sucursal=self.otra_sucursal)
        self.entrar_como("MESERO")
        self.client.post(reverse("operativo:asignar_mesa", args=[orden.pk]), {"mesa": self.mesa.pk})
        self.client.post(reverse("operativo:asignar_mesa", args=[orden.pk]), {"mesa": otra.pk})
        orden.refresh_from_db()
        self.assertIsNone(orden.mesa)
        self.assertEqual(self.mesa.ordenes.get(), ocupante)

    def test_cu_ped_04_solo_personal_de_sala(self):
        orden = self.crear_sin_mesa()
        self.entrar_como("JEFE_COCINA")
        self.assertEqual(self.client.post(reverse("operativo:asignar_mesa", args=[orden.pk]), {"mesa": self.mesa.pk}).status_code, 403)


class UbicacionSucursalTests(CasoDeUsoTestCase):
    def datos(self, **extra):
        return {"restaurante": self.restaurante.pk, "nombre": "Sur", "direccion": "", "telefono": "", "activo": "on", **extra}

    def test_cu_adm_19_guarda_latitud_y_longitud(self):
        form = SucursalForm(self.datos(latitud="6.2442", longitud="-75.5812"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.save().tiene_ubicacion)

    def test_cu_adm_19_exige_las_dos_coordenadas(self):
        self.assertFalse(SucursalForm(self.datos(latitud="6.2442", longitud="")).is_valid())
        self.assertFalse(SucursalForm(self.datos(latitud="95", longitud="10")).is_valid())

    def test_cu_adm_19_el_formulario_muestra_el_mapa(self):
        self.entrar_como("ADMINISTRADOR")
        self.assertContains(self.client.get(reverse("restaurantes:sucursal_crear")), "mapa-sucursal")

    def test_distancia_bogota_medellin(self):
        self.assertAlmostEqual(distancia_km(4.711, -74.0721, 6.2442, -75.5812), 239, delta=5)
