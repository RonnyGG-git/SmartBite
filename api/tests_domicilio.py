from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from core.testing import crear_escenario, crear_usuario
from cuentas.models import Usuario
from domicilio.models import Domicilio
from operativo.models import Mesa, Orden
from restaurantes.models import Restaurante, Sucursal

from .tests_movil import cliente_con_token


class DomicilioBase(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.cliente = crear_usuario("CLIENTE", email="cliente@test.co")
        self.api_cliente = cliente_con_token(self.cliente)
        self.domiciliario = crear_usuario("DOMICILIARIO", email="moto@test.co")
        self.api_moto = cliente_con_token(self.domiciliario)

    def crear_direccion(self):
        r = self.api_cliente.post(reverse("api:direcciones-list"), {
            "etiqueta": "Casa", "direccion": "Calle 10 # 5-20", "referencia": "Portón verde",
            "latitud": "4.600000", "longitud": "-74.080000",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()

    def pedir(self, direccion_id, telefono="3001234567"):
        return self.api_cliente.post(reverse("api:domicilios-cliente-list"), {
            "sucursal": self.d["centro"].pk, "direccion": direccion_id, "telefono": telefono,
            "lineas": [{"producto": self.d["bandeja"].pk, "cantidad": 2}],
        }, format="json")

    def llevar_a_lista(self, domicilio_id):
        orden = Domicilio.objects.get(pk=domicilio_id).orden
        orden.cambiar_estado(Orden.PENDIENTE)
        orden.cambiar_estado(Orden.EN_PREPARACION, tiempo_estimado_min=10)
        orden.cambiar_estado(Orden.LISTA)


class FlujoCompletoTests(DomicilioBase):
    def test_de_la_solicitud_a_la_entrega_con_codigo(self):
        direccion = self.crear_direccion()
        self.assertTrue(direccion["principal"])

        r = self.pedir(direccion["id"])
        self.assertEqual(r.status_code, 201, r.content)
        pedido = r.json()
        self.assertEqual(pedido["estado"], Domicilio.SOLICITADO)
        self.assertEqual(pedido["orden"]["estado"], Orden.POR_CONFIRMAR)
        self.assertEqual(pedido["orden"]["tipo_consumo"], Orden.DOMICILIO)
        self.assertEqual(len(pedido["codigo_entrega"]), 4)
        domicilio_id = pedido["id"]

        orden = Domicilio.objects.get(pk=domicilio_id).orden
        orden.cambiar_estado(Orden.PENDIENTE)
        self.assertEqual(Domicilio.objects.get(pk=domicilio_id).estado, Domicilio.CONFIRMADO)

        cocina = cliente_con_token(crear_usuario("JEFE_COCINA"))
        cocina.post(reverse("api:cocina-iniciar", args=[orden.pk]), {"tiempo_estimado": 15}, format="json")
        self.assertEqual(Domicilio.objects.get(pk=domicilio_id).estado, Domicilio.EN_COCINA)
        cocina.post(reverse("api:cocina-listo", args=[orden.pk]))
        self.assertEqual(Domicilio.objects.get(pk=domicilio_id).estado, Domicilio.LISTO_PARA_RECOGER)

        disponibles = self.api_moto.get(reverse("api:domiciliario-disponibles")).json()
        self.assertEqual([x["id"] for x in disponibles], [domicilio_id])
        self.assertNotIn("codigo_entrega", disponibles[0])

        r = self.api_moto.post(reverse("api:domiciliario-tomar", args=[domicilio_id]))
        self.assertEqual(r.json()["estado"], Domicilio.ASIGNADO)

        otro = cliente_con_token(crear_usuario("DOMICILIARIO", email="otro@test.co"))
        r = otro.post(reverse("api:domiciliario-tomar", args=[domicilio_id]))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "ya_tomado")

        r = self.api_moto.post(reverse("api:domiciliario-recoger", args=[domicilio_id]))
        self.assertEqual(r.json()["estado"], Domicilio.EN_CAMINO)
        r = self.api_moto.post(reverse("api:domiciliario-ubicacion", args=[domicilio_id]), {"latitud": "4.605", "longitud": "-74.081"}, format="json")
        self.assertEqual(r.status_code, 200)

        seguimiento = self.api_cliente.get(reverse("api:domicilios-cliente-detail", args=[domicilio_id])).json()
        self.assertEqual(seguimiento["lat_actual"], "4.605000")
        self.assertEqual(seguimiento["domiciliario"], self.domiciliario.nombre)

        r = self.api_moto.post(reverse("api:domiciliario-entregar", args=[domicilio_id]), {"codigo": "0000" if pedido["codigo_entrega"] != "0000" else "1111"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("codigo", r.json()["errores"])
        self.assertEqual(Domicilio.objects.get(pk=domicilio_id).intentos_codigo, 1)

        r = self.api_moto.post(reverse("api:domiciliario-entregar", args=[domicilio_id]), {"codigo": pedido["codigo_entrega"]}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["estado"], Domicilio.ENTREGADO)
        self.assertEqual(r.json()["orden"]["estado"], Orden.ENTREGADA)
        self.assertIsNotNone(Domicilio.objects.get(pk=domicilio_id).entregado_en)


class ReglasTests(DomicilioBase):
    def test_sin_cuenta_no_se_pide_a_domicilio(self):
        r = APIClient().post(reverse("api:domicilios-cliente-list"), {}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_un_mesero_no_usa_las_rutas_de_cliente(self):
        mesero = cliente_con_token(crear_usuario("MESERO"))
        self.assertEqual(mesero.get(reverse("api:domicilios-cliente-list")).status_code, 403)

    def test_exige_telefono(self):
        direccion = self.crear_direccion()
        r = self.pedir(direccion["id"], telefono="")
        self.assertEqual(r.status_code, 400)
        self.assertIn("telefono", r.json()["errores"])

    def test_no_acepta_direccion_ajena(self):
        otro = cliente_con_token(crear_usuario("CLIENTE", email="otro.cliente@test.co"))
        ajena = otro.post(reverse("api:direcciones-list"), {"direccion": "x", "latitud": "4.6", "longitud": "-74.0"}, format="json").json()
        self.assertEqual(self.pedir(ajena["id"]).status_code, 400)

    def test_cancelar_solo_antes_de_confirmar(self):
        domicilio_id = self.pedir(self.crear_direccion()["id"]).json()["id"]
        r = self.api_cliente.post(reverse("api:domicilios-cliente-cancelar", args=[domicilio_id]))
        self.assertEqual(r.json()["estado"], Domicilio.CANCELADO)

        otro_id = self.pedir(self.crear_direccion()["id"]).json()["id"]
        Domicilio.objects.get(pk=otro_id).orden.cambiar_estado(Orden.PENDIENTE)
        r = self.api_cliente.post(reverse("api:domicilios-cliente-cancelar", args=[otro_id]))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "ya_confirmado")

    def test_no_se_toma_antes_de_estar_listo(self):
        domicilio_id = self.pedir(self.crear_direccion()["id"]).json()["id"]
        r = self.api_moto.post(reverse("api:domiciliario-tomar", args=[domicilio_id]))
        self.assertEqual(r.json()["code"], "no_listo")

    def test_codigo_se_bloquea_tras_cinco_intentos(self):
        pedido = self.pedir(self.crear_direccion()["id"]).json()
        self.llevar_a_lista(pedido["id"])
        self.api_moto.post(reverse("api:domiciliario-tomar", args=[pedido["id"]]))
        self.api_moto.post(reverse("api:domiciliario-recoger", args=[pedido["id"]]))
        malo = "0000" if pedido["codigo_entrega"] != "0000" else "1111"
        for _ in range(5):
            self.api_moto.post(reverse("api:domiciliario-entregar", args=[pedido["id"]]), {"codigo": malo}, format="json")
        r = self.api_moto.post(reverse("api:domiciliario-entregar", args=[pedido["id"]]), {"codigo": pedido["codigo_entrega"]}, format="json")
        self.assertEqual(r.json()["code"], "codigo_bloqueado")

    def test_domiciliario_de_otro_restaurante_no_lo_ve(self):
        pedido = self.pedir(self.crear_direccion()["id"]).json()
        self.llevar_a_lista(pedido["id"])
        otro_rest = Restaurante.objects.create(nombre="Otro", nif="1", email="o@o.co", direccion="x")
        ajeno = cliente_con_token(crear_usuario("DOMICILIARIO", email="ajeno@test.co", restaurante=otro_rest))
        self.assertEqual(ajeno.get(reverse("api:domiciliario-disponibles")).json(), [])
        self.assertEqual(ajeno.post(reverse("api:domiciliario-tomar", args=[pedido["id"]])).status_code, 404)

    def test_solo_el_asignado_comparte_ubicacion(self):
        pedido = self.pedir(self.crear_direccion()["id"]).json()
        self.llevar_a_lista(pedido["id"])
        self.api_moto.post(reverse("api:domiciliario-tomar", args=[pedido["id"]]))
        otro = cliente_con_token(crear_usuario("DOMICILIARIO", email="otro@test.co"))
        r = otro.post(reverse("api:domiciliario-ubicacion", args=[pedido["id"]]), {"latitud": "4.6", "longitud": "-74.0"}, format="json")
        self.assertEqual(r.json()["code"], "no_asignado")

    def test_el_cliente_edita_su_perfil(self):
        r = self.api_cliente.patch(reverse("api:perfil_cliente"), {"nombre": "Luisa", "telefono": "3109998877"}, format="json")
        self.assertEqual(r.json()["telefono"], "3109998877")
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Luisa")


class RegistroClienteTests(TestCase):
    def setUp(self):
        crear_escenario()

    @mock.patch("cuentas.otp.secrets.randbelow", return_value=4321)
    def test_registro_y_verificacion(self, _):
        api = APIClient()
        r = api.post(reverse("api:registro_cliente"), {
            "nombre": "Sofía", "email": "sofia@test.co", "telefono": "3015550000",
            "password1": "ClaveSegura#2026", "password2": "ClaveSegura#2026",
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        usuario = Usuario.objects.get(email="sofia@test.co")
        self.assertEqual(usuario.rol.nombre, "CLIENTE")
        self.assertEqual(usuario.perfil_cliente.telefono, "3015550000")
        r = api.post(reverse("api:verificar"), {"email": "sofia@test.co", "codigo": "4321"}, format="json")
        self.assertEqual(r.json()["usuario"]["rol"], "CLIENTE")


class PedidoMesaTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()

    def test_qr_de_la_mesa_sin_cuenta(self):
        api = APIClient()
        info = api.get(reverse("api:pedido_mesa", args=[self.d["mesa"].pk])).json()
        self.assertTrue(info["disponible"])
        cuerpo = {"tipo_consumo": "PARA_LLEVAR", "nombre": "Ana", "lineas": [{"producto": self.d["bandeja"].pk, "cantidad": 1}]}
        r = api.post(reverse("api:pedido_mesa", args=[self.d["mesa"].pk]), cuerpo, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["orden"]["estado"], Orden.PENDIENTE)
        self.assertEqual(Mesa.objects.get(pk=self.d["mesa"].pk).estado, Mesa.OCUPADA)
        r = api.post(reverse("api:pedido_mesa", args=[self.d["mesa"].pk]), cuerpo, format="json")
        self.assertEqual(r.json()["code"], "mesa_ocupada")

    def test_producto_de_otra_sucursal(self):
        cuerpo = {"tipo_consumo": "EN_RESTAURANTE", "lineas": [{"producto": self.d["ajiaco"].pk, "cantidad": 1}]}
        r = APIClient().post(reverse("api:pedido_mesa", args=[self.d["mesa"].pk]), cuerpo, format="json")
        self.assertEqual(r.json()["code"], "no_disponible")
        self.assertEqual(Mesa.objects.get(pk=self.d["mesa"].pk).estado, Mesa.DISPONIBLE)


class PanelWebTests(DomicilioBase):
    def test_domiciliario_entra_al_panel_y_al_mapa(self):
        pedido = self.pedir(self.crear_direccion()["id"]).json()
        self.client.force_login(self.domiciliario)
        self.assertEqual(self.client.get(reverse("domicilio:panel")).status_code, 200)
        self.assertContains(self.client.get(reverse("domicilio:seguimiento", args=[pedido["id"]])), "mapa-domicilio")

    def test_mesero_no_entra_al_panel(self):
        self.client.force_login(crear_usuario("MESERO"))
        self.assertNotEqual(self.client.get(reverse("domicilio:panel")).status_code, 200)

    def test_cliente_web_aterriza_en_su_inicio(self):
        self.client.force_login(self.cliente)
        r = self.client.get(reverse("cuentas:login"))
        self.assertRedirects(r, reverse("cliente:inicio"), fetch_redirect_response=False)
