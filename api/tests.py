from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.testing import crear_escenario, crear_usuario
from inventario.models import ItemInventario


class MenuPublicoTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.cliente = APIClient()
        self.url = reverse("api:menu")

    def nombres(self, respuesta):
        return [p["nombre"] for p in respuesta.json()["results"]]

    def test_sin_mesa_no_mezcla_menus_de_restaurantes(self):
        respuesta = self.cliente.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.nombres(respuesta), [])

    def test_con_mesa_filtra_por_la_sucursal_de_la_mesa(self):
        respuesta = self.cliente.get(self.url, {"mesa": self.d["mesa"].pk})
        self.assertEqual(self.nombres(respuesta), ["Bandeja paisa"])

    def test_no_muestra_platillos_no_disponibles(self):
        self.d["bandeja"].disponible = False
        self.d["bandeja"].save()
        respuesta = self.cliente.get(self.url, {"mesa": self.d["mesa"].pk})
        self.assertEqual(self.nombres(respuesta), [])

    def test_trae_la_categoria_y_el_precio(self):
        platillo = self.cliente.get(self.url, {"mesa": self.d["mesa"].pk}).json()["results"][0]
        self.assertEqual(platillo["categoria"], {"id": self.d["categoria"].pk, "nombre": "Platos fuertes"})
        self.assertEqual(platillo["precio"], "32000.00")

    def test_respuesta_paginada(self):
        cuerpo = self.cliente.get(self.url, {"mesa": self.d["mesa"].pk}).json()
        self.assertEqual(cuerpo["count"], 1)
        self.assertIn("next", cuerpo)

    def test_mesa_inexistente_da_404_con_formato_de_error(self):
        respuesta = self.cliente.get(self.url, {"mesa": 9999})
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(respuesta.json()["code"], "not_found")
        self.assertIn("detail", respuesta.json())

    def test_mesa_inactiva_da_404(self):
        self.d["mesa"].activa = False
        self.d["mesa"].save()
        self.assertEqual(self.cliente.get(self.url, {"mesa": self.d["mesa"].pk}).status_code, 404)

    def test_mesa_no_numerica_da_400(self):
        respuesta = self.cliente.get(self.url, {"mesa": "abc"})
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["code"], "invalid")
        self.assertIn("mesa", respuesta.json()["errores"])

    def test_no_acepta_escritura(self):
        self.assertEqual(self.cliente.post(self.url, {}).status_code, 405)


class TokenTests(TestCase):
    def setUp(self):
        crear_escenario()
        self.usuario = crear_usuario("JEFE_INVENTARIO")
        self.cliente = APIClient()
        self.url = reverse("api:token")

    def test_credenciales_correctas_devuelven_token(self):
        respuesta = self.cliente.post(self.url, {"email": self.usuario.email, "password": "x"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["token"], Token.objects.get(user=self.usuario).key)

    def test_pedirlo_dos_veces_devuelve_el_mismo_token(self):
        primero = self.cliente.post(self.url, {"email": self.usuario.email, "password": "x"}).json()["token"]
        segundo = self.cliente.post(self.url, {"email": self.usuario.email, "password": "x"}).json()["token"]
        self.assertEqual(primero, segundo)

    def test_contrasena_incorrecta_da_400(self):
        respuesta = self.cliente.post(self.url, {"email": self.usuario.email, "password": "mal"})
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.json()["code"], "credenciales_invalidas")

    def test_usuario_inactivo_no_obtiene_token(self):
        self.usuario.is_active = False
        self.usuario.save()
        respuesta = self.cliente.post(self.url, {"email": self.usuario.email, "password": "x"})
        self.assertEqual(respuesta.status_code, 400)


class InventarioPermisosTests(TestCase):
    def setUp(self):
        d = crear_escenario()
        self.item = ItemInventario.objects.create(
            nombre="Leche entera", unidad_medida="L", stock_actual=3, stock_minimo=5, sucursal=d["centro"]
        )
        self.cliente = APIClient()
        self.url = reverse("api:items-inventario-list")

    def con_token(self, rol):
        usuario = crear_usuario(rol)
        token, _ = Token.objects.get_or_create(user=usuario)
        self.cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_sin_token_da_401(self):
        respuesta = self.cliente.get(self.url)
        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.json()["code"], "not_authenticated")

    def test_mesero_da_403(self):
        self.con_token("MESERO")
        respuesta = self.cliente.get(self.url)
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(respuesta.json()["code"], "permission_denied")

    def test_cajero_da_403(self):
        self.con_token("CAJERO")
        self.assertEqual(self.cliente.get(self.url).status_code, 403)

    def test_jefe_de_cocina_puede_consultar(self):
        self.con_token("JEFE_COCINA")
        self.assertEqual(self.cliente.get(self.url).status_code, 200)

    def test_jefe_de_inventario_ve_el_stock_bajo(self):
        self.con_token("JEFE_INVENTARIO")
        item = self.cliente.get(self.url).json()["results"][0]
        self.assertEqual(item["nombre"], "Leche entera")
        self.assertEqual(item["stock_actual"], 3)
        self.assertTrue(item["stock_bajo"])

    def test_detalle_de_un_item(self):
        self.con_token("ADMINISTRADOR")
        respuesta = self.cliente.get(reverse("api:items-inventario-detail", args=[self.item.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["id"], self.item.pk)

    def test_es_de_solo_lectura(self):
        self.con_token("ADMINISTRADOR")
        self.assertEqual(self.cliente.post(self.url, {"nombre": "X"}).status_code, 405)

    def test_la_sesion_web_tambien_sirve(self):
        self.cliente.force_login(crear_usuario("JEFE_INVENTARIO"))
        self.assertEqual(self.cliente.get(self.url).status_code, 200)


class AjusteStockApiTests(TestCase):
    def setUp(self):
        d = crear_escenario()
        self.item = ItemInventario.objects.create(nombre="Leche", stock_actual=10, stock_minimo=5, sucursal=d["centro"])
        self.cliente = APIClient()
        self.url = reverse("api:items-inventario-ajustar", args=[self.item.pk])
        self.datos = {"tipo": "SALIDA", "cantidad": 7, "motivo": "Consumo de cocina"}

    def con_token(self, rol):
        token, _ = Token.objects.get_or_create(user=crear_usuario(rol))
        self.cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_jefe_de_inventario_ajusta(self):
        self.con_token("JEFE_INVENTARIO")
        respuesta = self.cliente.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 201)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["item"]["stock_actual"], 3)
        self.assertTrue(cuerpo["item"]["stock_bajo"])
        self.assertEqual((cuerpo["movimiento"]["tipo"], cuerpo["movimiento"]["cantidad"]), ("SALIDA", 7))
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 3)

    def test_acepta_json(self):
        self.con_token("ADMINISTRADOR")
        respuesta = self.cliente.post(self.url, {"tipo": "ENTRADA", "cantidad": 5, "motivo": "x"}, format="json")
        self.assertEqual(respuesta.json()["item"]["stock_actual"], 15)

    def test_jefe_de_cocina_puede_ver_pero_no_ajustar(self):
        self.con_token("JEFE_COCINA")
        respuesta = self.cliente.post(self.url, self.datos)
        self.assertEqual(respuesta.status_code, 403)
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)

    def test_sin_token_da_401(self):
        self.assertEqual(self.cliente.post(self.url, self.datos).status_code, 401)

    def test_cantidad_invalida_da_400_por_campo(self):
        self.con_token("JEFE_INVENTARIO")
        respuesta = self.cliente.post(self.url, {**self.datos, "cantidad": 0})
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("cantidad", respuesta.json()["errores"])

    def test_tipo_invalido_da_400(self):
        self.con_token("JEFE_INVENTARIO")
        respuesta = self.cliente.post(self.url, {**self.datos, "tipo": "AJUSTE"})
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("tipo", respuesta.json()["errores"])

    def test_item_inexistente_da_404(self):
        self.con_token("JEFE_INVENTARIO")
        url = reverse("api:items-inventario-ajustar", args=[9999])
        self.assertEqual(self.cliente.post(url, self.datos).status_code, 404)


class ErroresDelDominioTests(SimpleTestCase):
    def manejar(self, exc):
        from api.excepciones import manejador_de_errores
        return manejador_de_errores(exc, {})

    def test_mensaje_con_codigo(self):
        respuesta = self.manejar(DjangoValidationError("No se puede pasar de LISTA a PENDIENTE.",
                                                       code="transicion_invalida"))
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data, {"detail": "No se puede pasar de LISTA a PENDIENTE.",
                                          "code": "transicion_invalida"})

    def test_mensaje_sin_codigo_usa_invalid(self):
        respuesta = self.manejar(DjangoValidationError("Algo no vale."))
        self.assertEqual(respuesta.data, {"detail": "Algo no vale.", "code": "invalid"})

    def test_errores_por_campo(self):
        respuesta = self.manejar(DjangoValidationError({"cantidad": ["Debe ser positiva."]}))
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data["code"], "invalid")
        self.assertEqual(respuesta.data["errores"], {"cantidad": ["Debe ser positiva."]})

    def test_otros_errores_siguen_siendo_500(self):
        self.assertIsNone(self.manejar(ValueError("bug")))


class DocumentacionTests(TestCase):
    def test_esquema_openapi(self):
        respuesta = self.client.get(reverse("api:esquema"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b"/api/v1/menu/", respuesta.content)

    def test_swagger(self):
        self.assertEqual(self.client.get(reverse("api:docs")).status_code, 200)
