from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from caja.models import Factura, MetodoPago, Pago
from core.testing import crear_escenario, crear_usuario
from operativo.models import DetalleOrden, Mesa, Orden
from restaurantes.models import Restaurante, Sucursal


def api_de(usuario):
    cliente = APIClient()
    token, _ = Token.objects.get_or_create(user=usuario)
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return cliente


class CajaApiTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.cajero = crear_usuario("CAJERO")
        self.api = api_de(self.cajero)
        self.efectivo = MetodoPago.objects.create(nombre="Efectivo")
        self.tarjeta = MetodoPago.objects.create(nombre="Tarjeta")
        self.orden = Orden.objects.create(mesa=self.d["mesa"], sucursal=self.d["centro"], estado=Orden.LISTA)
        DetalleOrden.objects.create(orden=self.orden, producto=self.d["bandeja"], cantidad=2, precio_unitario=Decimal("32000"))
        Mesa.objects.filter(pk=self.d["mesa"].pk).update(estado=Mesa.OCUPADA)

    def cobrar(self, **datos):
        return self.api.post(reverse("api:caja_cobrar", args=[self.orden.pk]), datos, format="json")

    def test_lista_metodos_activos_y_marca_los_de_pasarela(self):
        MetodoPago.objects.create(nombre="Viejo", activo=False)
        r = self.api.get(reverse("api:caja_metodos"))
        self.assertEqual({m["nombre"]: m["usa_pasarela"] for m in r.json()}, {"Efectivo": False, "Tarjeta": True})

    def test_la_cuenta_trae_saldo_y_pagos(self):
        r = self.api.get(reverse("api:caja_cuenta", args=[self.orden.pk]))
        self.assertEqual(r.json()["saldo_pendiente"], "64000.00")
        self.assertTrue(r.json()["cobrable"])
        self.assertEqual(r.json()["pagos"], [])

    def test_pago_parcial_deja_saldo_y_no_cierra(self):
        r = self.cobrar(metodo=self.efectivo.pk, monto="40000")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["saldo_pendiente"], "24000.00")
        self.assertEqual(r.json()["orden"]["estado"], Orden.LISTA)

    def test_pago_completo_entrega_libera_mesa_factura_y_calcula_cambio(self):
        r = self.cobrar(metodo=self.efectivo.pk, monto="64000", propina="5000", efectivo_recibido="70000")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["orden"]["estado"], Orden.ENTREGADA)
        self.assertEqual(r.json()["cambio"], "1000.00")
        self.assertIsNotNone(r.json()["factura"])
        self.d["mesa"].refresh_from_db()
        self.assertEqual(self.d["mesa"].estado, Mesa.DISPONIBLE)
        self.assertEqual(Pago.objects.get().cobrado_por, self.cajero)

    def test_no_se_cobra_mas_del_saldo(self):
        r = self.cobrar(metodo=self.efectivo.pk, monto="90000")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "cobro_invalido")

    def test_orden_de_mesa_sin_terminar_no_es_cobrable(self):
        Orden.objects.filter(pk=self.orden.pk).update(estado=Orden.EN_PREPARACION)
        self.assertEqual(self.cobrar(metodo=self.efectivo.pk, monto="1000").json()["code"], "no_cobrable")

    def test_tarjeta_devuelve_el_checkout_de_la_pasarela(self):
        r = self.cobrar(metodo=self.tarjeta.pk, monto="64000")
        self.assertEqual(r.status_code, 202)
        self.assertTrue(r.json()["checkout"].startswith("http"))
        self.assertEqual(Pago.objects.get().estado, Pago.PENDIENTE)

    def test_qr_de_cobro_trae_enlace_e_imagen(self):
        r = self.api.post(reverse("api:caja_qr", args=[self.orden.pk]))
        self.assertTrue(r.json()["url"].startswith("http"))
        self.assertTrue(len(r.json()["qr_png_base64"]) > 100)

    def test_aceptar_y_rechazar_para_llevar(self):
        llevar = Orden.objects.create(sucursal=self.d["centro"], estado=Orden.POR_CONFIRMAR)
        r = self.api.post(reverse("api:caja_aceptar", args=[llevar.pk]))
        self.assertEqual(r.json()["estado"], Orden.PENDIENTE)
        r = self.api.post(reverse("api:caja_rechazar", args=[llevar.pk]))
        self.assertEqual(r.json()["code"], "no_por_confirmar")

    def test_facturas_y_ventas_del_restaurante(self):
        self.cobrar(metodo=self.efectivo.pk, monto="64000")
        factura = Factura.objects.get()
        self.assertEqual([f["id"] for f in self.api.get(reverse("api:caja_facturas")).json()["results"]], [factura.pk])
        detalle = self.api.get(reverse("api:caja_factura", args=[factura.pk])).json()
        self.assertEqual(detalle["codigo"], factura.codigo)
        self.assertEqual(len(detalle["detalle"]["lineas"]), 1)
        self.assertEqual(self.api.get(reverse("api:caja_ventas")).json()["count"], 1)

    def test_caja_de_otro_restaurante_no_ve_ni_cobra(self):
        otro = Restaurante.objects.create(nombre="Otro", nif="7", email="o@o.co", direccion="x")
        Sucursal.objects.create(restaurante=otro, nombre="S")
        ajeno = api_de(crear_usuario("CAJERO", email="ajeno@test.co", restaurante=otro))
        self.assertEqual(ajeno.get(reverse("api:caja_cuenta", args=[self.orden.pk])).status_code, 404)
        r = ajeno.post(reverse("api:caja_cobrar", args=[self.orden.pk]), {"metodo": self.efectivo.pk, "monto": "1"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_el_mesero_no_cobra(self):
        mesero = api_de(crear_usuario("MESERO", email="mes@test.co"))
        self.assertEqual(mesero.post(reverse("api:caja_cobrar", args=[self.orden.pk]), {}, format="json").status_code, 403)


class PagoDelClienteDesdeLaAppTests(TestCase):
    def setUp(self):
        from api.views_publico import codigo_de

        self.d = crear_escenario()
        self.orden = Orden.objects.create(mesa=self.d["mesa"], sucursal=self.d["centro"], estado=Orden.LISTA)
        DetalleOrden.objects.create(orden=self.orden, producto=self.d["bandeja"], cantidad=1, precio_unitario=Decimal("32000"))
        self.codigo = codigo_de(self.orden)
        self.api = APIClient()

    def pedir(self, codigo=None):
        return self.api.post(reverse("api:pedido_publico_pago", args=[codigo or self.codigo]))

    def test_devuelve_la_pagina_de_pago_con_wompi_y_efectivo(self):
        r = self.pedir()
        self.assertEqual(r.status_code, 200)
        self.assertIn("/caja/pagar/", r.json()["url"])
        self.assertEqual(r.json()["saldo_pendiente"], "32000.00")
        self.assertEqual(r.json()["en_linea"], "simulada")
        pagina = self.client.get(r.json()["url"].split("testserver", 1)[1])
        self.assertContains(pagina, "Pagar en línea")
        self.assertContains(pagina, "Pagar en efectivo en caja")

    def test_reutiliza_el_enlace_vigente(self):
        self.assertEqual(self.pedir().json()["url"], self.pedir().json()["url"])

    def test_codigo_falso_no_encuentra_el_pedido(self):
        self.assertEqual(self.pedir("falso").status_code, 404)

    def test_no_se_paga_un_pedido_por_confirmar_ni_uno_cerrado(self):
        Orden.objects.filter(pk=self.orden.pk).update(estado=Orden.POR_CONFIRMAR)
        self.assertEqual(self.pedir().json()["code"], "por_confirmar")
        Orden.objects.filter(pk=self.orden.pk).update(estado=Orden.ENTREGADA)
        self.assertEqual(self.pedir().json()["code"], "orden_final")

    def test_por_cobrar_avisa_cuando_el_cliente_pagara_en_efectivo(self):
        from caja.models import EnlacePago
        from caja.qr import pedir_pago_en_efectivo

        cajero = api_de(crear_usuario("CAJERO"))
        Orden.objects.filter(pk=self.orden.pk).update(cuenta_solicitada_en=self.orden.creado_en)
        self.assertFalse(cajero.get(reverse("api:por_cobrar")).json()[0]["pagara_efectivo"])
        self.pedir()
        pedir_pago_en_efectivo(EnlacePago.objects.get(orden=self.orden))
        self.assertTrue(cajero.get(reverse("api:por_cobrar")).json()[0]["pagara_efectivo"])

