from unittest import mock

from django.test import TestCase
from django.urls import reverse

from core.testing import crear_escenario, crear_usuario
from cuentas.models import Usuario
from domicilio.models import DireccionCliente, Domicilio, PerfilCliente
from operativo.models import Orden


class InicioClienteTests(TestCase):
    def test_boton_cliente_del_login_lleva_al_inicio_del_cliente(self):
        r = self.client.get(reverse("cuentas:login"))
        self.assertContains(r, reverse("cliente:inicio"))

    def test_inicio_sin_sesion_muestra_restaurantes_qr_y_registro_en_la_esquina(self):
        r = self.client.get(reverse("cliente:inicio"))
        self.assertContains(r, reverse("cliente:restaurantes"))
        self.assertContains(r, reverse("cliente:escanear"))
        self.assertContains(r, reverse("cuentas:registro_cliente"))
        self.assertContains(r, "Iniciar sesión")

    def test_inicio_con_cliente_muestra_su_cuenta(self):
        cliente = crear_usuario("CLIENTE", email="cli@test.co")
        self.client.force_login(cliente)
        r = self.client.get(reverse("cliente:inicio"))
        self.assertContains(r, reverse("cliente:cuenta"))
        self.assertNotContains(r, reverse("cuentas:registro_cliente"))

    def test_escanear_responde(self):
        self.assertEqual(self.client.get(reverse("cliente:escanear")).status_code, 200)


class RegistroClienteWebTests(TestCase):
    @mock.patch("cuentas.otp.enviar_codigo")
    def test_registro_crea_cliente_sin_verificar_con_telefono(self, enviar):
        r = self.client.post(reverse("cuentas:registro_cliente"), {
            "nombre": "Ana Cliente", "email": "ana@test.co", "telefono": "3001112233",
            "password1": "ClaveSegura2026!", "password2": "ClaveSegura2026!",
        })
        self.assertRedirects(r, reverse("cuentas:verificar"), fetch_redirect_response=False)
        usuario = Usuario.objects.get(email="ana@test.co")
        self.assertEqual(usuario.rol.nombre, "CLIENTE")
        self.assertFalse(usuario.email_verificado)
        self.assertEqual(PerfilCliente.objects.get(usuario=usuario).telefono, "3001112233")
        enviar.assert_called_once()

    def test_cliente_verificado_entra_a_su_inicio(self):
        crear_usuario("CLIENTE", email="beto@test.co")
        r = self.client.post(reverse("cuentas:login"), {"username": "beto@test.co", "password": "x"})
        self.assertRedirects(r, reverse("cliente:inicio"), fetch_redirect_response=False)


class CuentaClienteTests(TestCase):
    def setUp(self):
        self.cliente = crear_usuario("CLIENTE", email="cli@test.co")
        self.client.force_login(self.cliente)

    def test_edita_sus_datos_de_contacto(self):
        r = self.client.post(reverse("cliente:cuenta"), {"nombre": "Nuevo Nombre", "telefono": "3109998877", "documento": "123"})
        self.assertRedirects(r, reverse("cliente:cuenta"))
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Nuevo Nombre")
        self.assertEqual(self.cliente.perfil_cliente.telefono, "3109998877")

    def test_agrega_direccion_y_la_primera_queda_principal(self):
        r = self.client.post(reverse("cliente:direccion_crear"), {
            "etiqueta": "Casa", "direccion": "Calle 10 # 5-20", "referencia": "",
            "latitud": "7.119300", "longitud": "-73.122700",
        })
        self.assertRedirects(r, reverse("cliente:cuenta"))
        self.assertTrue(DireccionCliente.objects.get(usuario=self.cliente).principal)

    def test_direccion_sin_punto_en_el_mapa_no_se_guarda(self):
        r = self.client.post(reverse("cliente:direccion_crear"), {"etiqueta": "Casa", "direccion": "Calle 1"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(DireccionCliente.objects.exists())

    def test_no_puede_editar_direccion_ajena(self):
        otro = crear_usuario("CLIENTE", email="otro@test.co")
        ajena = DireccionCliente.objects.create(usuario=otro, direccion="X", latitud=1, longitud=1)
        self.assertEqual(self.client.get(reverse("cliente:direccion_editar", args=[ajena.pk])).status_code, 404)

    def test_empleado_no_entra_a_la_cuenta_de_cliente(self):
        self.client.force_login(crear_usuario("MESERO", email="m@test.co"))
        self.assertEqual(self.client.get(reverse("cliente:cuenta")).status_code, 403)


class PedidoDomicilioWebTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.cliente = crear_usuario("CLIENTE", email="cli@test.co")
        self.direccion = DireccionCliente.objects.create(
            usuario=self.cliente, etiqueta="Casa", direccion="Calle 10 # 5-20", latitud="7.1193", longitud="-73.1227", principal=True,
        )

    def elegir_restaurante(self):
        self.client.get(reverse("cliente:sucursal", args=[self.d["centro"].pk]))

    def test_sin_cuenta_no_aparece_domicilio(self):
        self.elegir_restaurante()
        r = self.client.get(reverse("cliente:tipo_consumo"))
        self.assertNotContains(r, 'value="DOMICILIO"')
        self.assertContains(r, reverse("cuentas:registro_cliente"))
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": Orden.DOMICILIO})
        self.assertIsNone(self.client.session.get("cliente_tipo_consumo"))

    def test_en_la_mesa_no_aparece_domicilio_aunque_tenga_cuenta(self):
        self.client.force_login(self.cliente)
        self.client.get(reverse("cliente:mesa", args=[self.d["mesa"].pk]))
        self.assertNotContains(self.client.get(reverse("cliente:tipo_consumo")), 'value="DOMICILIO"')

    def test_flujo_completo_pide_a_domicilio_y_lo_sigue(self):
        self.client.force_login(self.cliente)
        self.elegir_restaurante()
        self.assertContains(self.client.get(reverse("cliente:tipo_consumo")), 'value="DOMICILIO"')
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": Orden.DOMICILIO})
        bandeja = self.d["bandeja"]
        self.client.post(reverse("cliente:carrito"), {f"cant_{bandeja.pk}": "2"})
        compra = self.client.get(reverse("cliente:compra"))
        self.assertContains(compra, "Entrega a domicilio")
        r = self.client.post(reverse("cliente:autopedido"), {
            f"cant_{bandeja.pk}": "2", "direccion": self.direccion.pk, "telefono": "3001234567",
        })
        domicilio = Domicilio.objects.get(cliente=self.cliente)
        self.assertRedirects(r, reverse("cliente:domicilio", args=[domicilio.pk]))
        self.assertEqual(domicilio.estado, Domicilio.SOLICITADO)
        self.assertEqual(domicilio.orden.tipo_consumo, Orden.DOMICILIO)
        self.assertEqual(domicilio.orden.estado, Orden.POR_CONFIRMAR)
        detalle = self.client.get(reverse("cliente:domicilio", args=[domicilio.pk]))
        self.assertContains(detalle, domicilio.codigo_entrega)
        self.assertContains(detalle, 'data-destino-lat="7.119300"')
        self.assertNotContains(detalle, "None")
        estado = self.client.get(reverse("cliente:domicilio_estado", args=[domicilio.pk])).json()
        self.assertEqual(estado["estado"], Domicilio.SOLICITADO)
        self.assertEqual(self.cliente.perfil_cliente.telefono, "3001234567")

    def test_sin_direcciones_lo_manda_a_crear_una(self):
        self.direccion.delete()
        self.client.force_login(self.cliente)
        self.elegir_restaurante()
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": Orden.DOMICILIO})
        self.client.post(reverse("cliente:carrito"), {f"cant_{self.d['bandeja'].pk}": "1"})
        r = self.client.get(reverse("cliente:compra"))
        self.assertTrue(r["Location"].startswith(reverse("cliente:direccion_crear")))

    def test_cancela_mientras_esta_solicitado_y_otro_cliente_no_lo_ve(self):
        self.client.force_login(self.cliente)
        self.elegir_restaurante()
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": Orden.DOMICILIO})
        bandeja = self.d["bandeja"]
        self.client.post(reverse("cliente:autopedido"), {
            f"cant_{bandeja.pk}": "1", "direccion": self.direccion.pk, "telefono": "3001234567",
        })
        domicilio = Domicilio.objects.get(cliente=self.cliente)
        self.client.force_login(crear_usuario("CLIENTE", email="otro@test.co"))
        self.assertEqual(self.client.get(reverse("cliente:domicilio", args=[domicilio.pk])).status_code, 404)
        self.client.force_login(self.cliente)
        self.client.post(reverse("cliente:domicilio_cancelar", args=[domicilio.pk]))
        domicilio.refresh_from_db()
        self.assertEqual(domicilio.estado, Domicilio.CANCELADO)
