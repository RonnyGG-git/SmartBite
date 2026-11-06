from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from caja.models import MetodoPago, Pago
from core.testing import crear_escenario, crear_usuario
from cuentas.models import Usuario
from operativo.models import Mesa, Orden
from restaurantes.models import Restaurante, Sucursal

CODIGO_FIJO = mock.patch("cuentas.otp.secrets.randbelow", return_value=1234)


def cliente_con_token(usuario):
    cliente = APIClient()
    token, _ = Token.objects.get_or_create(user=usuario)
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return cliente


class LoginTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.mesero = crear_usuario("MESERO")
        self.cliente = APIClient()

    def test_login_devuelve_token_y_perfil(self):
        r = self.cliente.post(reverse("api:login"), {"email": self.mesero.email, "password": "x"}, format="json")
        self.assertEqual(r.status_code, 200)
        cuerpo = r.json()
        self.assertEqual(cuerpo["token"], Token.objects.get(user=self.mesero).key)
        self.assertEqual(cuerpo["usuario"]["rol"], "MESERO")
        self.assertEqual(cuerpo["usuario"]["restaurante_actual"]["id"], self.d["restaurante"].pk)

    def test_clave_incorrecta(self):
        r = self.cliente.post(reverse("api:login"), {"email": self.mesero.email, "password": "mal"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "credenciales_invalidas")

    @CODIGO_FIJO
    def test_cuenta_sin_verificar_pide_codigo(self, _):
        self.mesero.email_verificado = False
        self.mesero.is_active = False
        self.mesero.save()
        r = self.cliente.post(reverse("api:login"), {"email": self.mesero.email, "password": "x"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["code"], "correo_sin_verificar")
        self.assertEqual(len(mail.outbox), 1)

    def test_yo_y_logout(self):
        cliente = cliente_con_token(self.mesero)
        self.assertEqual(cliente.get(reverse("api:yo")).json()["email"], self.mesero.email)
        self.assertEqual(cliente.post(reverse("api:logout")).status_code, 204)
        self.assertFalse(Token.objects.filter(user=self.mesero).exists())

    def test_yo_sin_token_da_401(self):
        self.assertEqual(self.cliente.get(reverse("api:yo")).status_code, 401)


class RegistroTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.cliente = APIClient()

    def datos(self, **extra):
        return {"nombre": "Ana", "email": "ana@test.co", "password1": "ClaveSegura#2026",
                "password2": "ClaveSegura#2026", **extra}

    @CODIGO_FIJO
    def test_empleado_con_codigo_se_registra_y_verifica(self, _):
        codigo = self.d["restaurante"].codigo_acceso
        r = self.cliente.post(reverse("api:registro_empleado"), self.datos(codigo=codigo.lower()), format="json")
        self.assertEqual(r.status_code, 201)
        usuario = Usuario.objects.get(email="ana@test.co")
        self.assertFalse(usuario.email_verificado)
        self.assertEqual(usuario.restaurante, self.d["restaurante"])

        r = self.cliente.post(reverse("api:verificar"), {"email": "ana@test.co", "codigo": "1234"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("token", r.json())
        self.assertIsNone(r.json()["usuario"]["rol"])
        usuario.refresh_from_db()
        self.assertTrue(usuario.email_verificado and usuario.is_active)

    def test_codigo_de_restaurante_invalido(self):
        r = self.cliente.post(reverse("api:registro_empleado"), self.datos(codigo="NOEXISTE"), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("codigo", r.json()["errores"])

    def test_claves_distintas(self):
        r = self.cliente.post(reverse("api:registro_admin"), self.datos(password2="otra"), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("password2", r.json()["errores"])

    @CODIGO_FIJO
    def test_admin_codigo_incorrecto(self, _):
        self.cliente.post(reverse("api:registro_admin"), self.datos(), format="json")
        r = self.cliente.post(reverse("api:verificar"), {"email": "ana@test.co", "codigo": "9999"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("codigo", r.json()["errores"])
        self.assertEqual(Usuario.objects.get(email="ana@test.co").rol.nombre, "ADMINISTRADOR")

    @CODIGO_FIJO
    def test_recuperar_contrasena(self, _):
        usuario = crear_usuario("CAJERO")
        Token.objects.create(user=usuario)
        r = self.cliente.post(reverse("api:recuperar"), {"email": usuario.email}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.cliente.post(reverse("api:recuperar_confirmar"), {
            "email": usuario.email, "codigo": "1234",
            "password1": "OtraClave#2026", "password2": "OtraClave#2026",
        }, format="json")
        self.assertEqual(r.status_code, 200)
        usuario.refresh_from_db()
        self.assertTrue(usuario.check_password("OtraClave#2026"))
        self.assertFalse(Token.objects.filter(user=usuario).exists())

    def test_recuperar_no_revela_si_existe(self):
        r = self.cliente.post(reverse("api:recuperar"), {"email": "nadie@test.co"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


class MeseroTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.mesero = crear_usuario("MESERO")
        self.api = cliente_con_token(self.mesero)

    def test_lista_mesas_del_restaurante(self):
        otro = Restaurante.objects.create(nombre="Otro", nif="1", email="o@o.co", direccion="x")
        Mesa.objects.create(numero=9, sucursal=Sucursal.objects.create(restaurante=otro, nombre="S"))
        r = self.api.get(reverse("api:mesas"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([m["numero"] for m in r.json()], [4])

    def test_flujo_orden(self):
        r = self.api.post(reverse("api:ordenes-list"), {"mesa": self.d["mesa"].pk, "cliente_nombre": "Luis"}, format="json")
        self.assertEqual(r.status_code, 201)
        orden_id = r.json()["id"]
        self.d["mesa"].refresh_from_db()
        self.assertEqual(self.d["mesa"].estado, Mesa.OCUPADA)

        r = self.api.post(reverse("api:ordenes-detalles", args=[orden_id]),
                          {"producto": self.d["bandeja"].pk, "cantidad": 2}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["total"], "64000.00")

        r = self.api.post(reverse("api:ordenes-list"), {"mesa": self.d["mesa"].pk}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "mesa_ocupada")

        r = self.api.post(reverse("api:ordenes-cancelar", args=[orden_id]))
        self.assertEqual(r.json()["estado"], Orden.CANCELADA)

    def test_producto_de_otra_sucursal_no_se_agrega(self):
        orden = Orden.objects.create(mesa=self.d["mesa"])
        r = self.api.post(reverse("api:ordenes-detalles", args=[orden.pk]),
                          {"producto": self.d["ajiaco"].pk, "cantidad": 1}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_solicitar_cuenta_solo_si_lista(self):
        orden = Orden.objects.create(mesa=self.d["mesa"])
        r = self.api.post(reverse("api:ordenes-solicitar-cuenta", args=[orden.pk]))
        self.assertEqual(r.json()["code"], "orden_no_lista")
        Orden.objects.filter(pk=orden.pk).update(estado=Orden.LISTA)
        r = self.api.post(reverse("api:ordenes-solicitar-cuenta", args=[orden.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.json()["cuenta_solicitada_en"])

    def test_mesero_no_entra_a_cocina(self):
        self.assertEqual(self.api.get(reverse("api:cocina-list")).status_code, 403)

    def test_encabezado_de_restaurante_ajeno_se_ignora(self):
        otro = Restaurante.objects.create(nombre="Otro", nif="1", email="o@o.co", direccion="x")
        r = self.api.get(reverse("api:yo"), HTTP_X_RESTAURANTE=str(otro.pk))
        self.assertEqual(r.json()["restaurante_actual"]["id"], self.d["restaurante"].pk)


class CocinaYCajaTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.orden = Orden.objects.create(mesa=self.d["mesa"])
        self.orden.detalles.create(producto=self.d["bandeja"], cantidad=1, precio_unitario=Decimal("32000"))

    def test_cocina_inicia_y_marca_lista(self):
        api = cliente_con_token(crear_usuario("JEFE_COCINA"))
        r = api.get(reverse("api:cocina-list"))
        self.assertEqual([o["id"] for o in r.json()], [self.orden.pk])
        self.assertEqual(r.json()[0]["faltantes"], [])

        r = api.post(reverse("api:cocina-iniciar", args=[self.orden.pk]), {"tiempo_estimado": 0}, format="json")
        self.assertEqual(r.status_code, 400)
        r = api.post(reverse("api:cocina-iniciar", args=[self.orden.pk]), {"tiempo_estimado": 15}, format="json")
        self.assertEqual(r.json()["estado"], Orden.EN_PREPARACION)
        r = api.post(reverse("api:cocina-listo", args=[self.orden.pk]))
        self.assertEqual(r.json()["estado"], Orden.LISTA)
        r = api.post(reverse("api:cocina-listo", args=[self.orden.pk]))
        self.assertEqual(r.status_code, 404)

    def test_caja_ve_cuentas_por_cobrar(self):
        api = cliente_con_token(crear_usuario("CAJERO"))
        self.assertEqual(api.get(reverse("api:por_cobrar")).json(), [])
        Orden.objects.filter(pk=self.orden.pk).update(estado=Orden.LISTA, cuenta_solicitada_en="2026-01-01T12:00Z")
        self.assertEqual([o["id"] for o in api.get(reverse("api:por_cobrar")).json()], [self.orden.pk])

    def test_entregar_exige_pago(self):
        api = cliente_con_token(crear_usuario("MESERO"))
        Orden.objects.filter(pk=self.orden.pk).update(estado=Orden.LISTA)
        r = api.post(reverse("api:ordenes-entregar", args=[self.orden.pk]))
        self.assertEqual(r.json()["code"], "orden_sin_pagar")
        Pago.objects.create(orden=self.orden, metodo_pago=MetodoPago.objects.create(nombre="Efectivo"), monto=Decimal("32000"))
        r = api.post(reverse("api:ordenes-entregar", args=[self.orden.pk]))
        self.assertEqual(r.json()["estado"], Orden.ENTREGADA)


class ClientePublicoTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.api = APIClient()

    def test_directorio_y_menu(self):
        nombres = [s["nombre"] for s in self.api.get(reverse("api:sucursales_publicas")).json()]
        self.assertEqual(sorted(nombres), ["Centro", "Norte"])
        menu = self.api.get(reverse("api:menu_sucursal", args=[self.d["centro"].pk])).json()
        self.assertEqual([p["nombre"] for p in menu], ["Bandeja paisa"])

    def test_pedido_y_seguimiento(self):
        r = self.api.post(reverse("api:pedido_publico"), {
            "sucursal": self.d["centro"].pk, "tipo_consumo": "PARA_LLEVAR", "nombre": "Sofía",
            "lineas": [{"producto": self.d["bandeja"].pk, "cantidad": 2}],
        }, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["orden"]["estado"], Orden.POR_CONFIRMAR)
        codigo = r.json()["codigo"]
        r = self.api.get(reverse("api:pedido_publico_detalle", args=[codigo]))
        self.assertEqual(r.json()["total"], "64000.00")

    def test_codigo_falso_da_404(self):
        self.assertEqual(self.api.get(reverse("api:pedido_publico_detalle", args=["123"])).status_code, 404)

    def test_producto_de_otra_sucursal_se_rechaza(self):
        r = self.api.post(reverse("api:pedido_publico"), {
            "sucursal": self.d["centro"].pk, "tipo_consumo": "PARA_LLEVAR",
            "lineas": [{"producto": self.d["ajiaco"].pk, "cantidad": 1}],
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "no_disponible")
