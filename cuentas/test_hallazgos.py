from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from catalogo.models import Categoria, Producto
from core.testing import crear_escenario, crear_usuario
from recetas.models import ProductoIngrediente
from restaurantes.forms import RestauranteForm, SucursalForm
from restaurantes.models import Restaurante


class H8AutoDesactivacionTests(TestCase):
    def setUp(self):
        self.admin = crear_usuario("ADMINISTRADOR")
        Restaurante.objects.create(
            nombre="La Ceiba", nif="900123456", email="hola@laceiba.co", direccion="Cra 7", administrador=self.admin
        )
        self.client.force_login(self.admin)

    def test_no_puede_desactivarse_a_si_mismo(self):
        url = reverse("cuentas:usuario_toggle_activo", args=[self.admin.pk])
        respuesta = self.client.post(url, follow=True)

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active, "H8 fallo: se desactivo a si mismo")
        self.assertContains(respuesta, "No puedes desactivar tu propia cuenta")

    def test_redirige_seguro_a_la_lista(self):
        url = reverse("cuentas:usuario_toggle_activo", args=[self.admin.pk])
        respuesta = self.client.post(url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], reverse("cuentas:usuarios_list"))

    def test_su_si_puede_desactivar_a_otro(self):
        otro = crear_usuario("MESERO")
        url = reverse("cuentas:usuario_toggle_activo", args=[otro.pk])
        self.client.post(url)
        otro.refresh_from_db()
        self.assertFalse(otro.is_active)


class H9CantidadMinimaTests(TestCase):
    def _validar(self, cantidad):
        campo = ProductoIngrediente._meta.get_field("cantidad_requerida")
        campo.run_validators(cantidad)

    def test_campo_tiene_minvaluevalidator(self):
        from django.core.validators import MinValueValidator

        campo = ProductoIngrediente._meta.get_field("cantidad_requerida")
        self.assertTrue(
            any(isinstance(v, MinValueValidator) for v in campo.validators),
            "H9 fallo: el campo no tiene MinValueValidator",
        )

    def test_rechaza_cero(self):
        with self.assertRaises(ValidationError):
            self._validar(Decimal("0"))

    def test_rechaza_negativo(self):
        with self.assertRaises(ValidationError):
            self._validar(Decimal("-1.500"))

    def test_acepta_el_minimo_exacto(self):
        self._validar(Decimal("0.001"))


class H11UnicidadProductoTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.categoria = Categoria.objects.get(nombre="Platos fuertes")

    def test_rechaza_nombre_repetido_en_la_misma_sucursal(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Producto.objects.create(
                    nombre="Bandeja paisa",
                    precio=Decimal("2"),
                    categoria=self.categoria,
                    sucursal=self.d["centro"],
                )

    def test_permite_mismo_nombre_en_sucursales_distintas(self):
        nuevo = Producto.objects.create(
            nombre="Ajiaco", precio=Decimal("3"), categoria=self.categoria, sucursal=self.d["centro"]
        )
        self.assertEqual(nuevo.sucursal, self.d["centro"])
        self.assertEqual(Producto.objects.filter(nombre="Ajiaco").count(), 2)


class G8ValidadoresFormularioTests(TestCase):
    def _payload(self, **overrides):
        datos = {
            "nombre": "La Ceiba",
            "nif": "900123456-1",
            "email": "hola@laceiba.co",
            "direccion": "Cra 7 # 12-30",
            "telefono": "+57 604 1234567",
            "telefono_secundario": "",
            "logo_url": "",
            "activo": True,
        }
        datos.update(overrides)
        return datos

    def test_telefono_invalido_se_rechaza(self):
        self.assertFalse(RestauranteForm(self._payload(telefono="abc")).is_valid())

    def test_nif_invalido_se_rechaza(self):
        self.assertFalse(RestauranteForm(self._payload(nif="no-es-un-nif")).is_valid())

    def test_url_con_esquema_peligroso_se_rechaza(self):
        self.assertFalse(RestauranteForm(self._payload(logo_url="javascript:alert(1)")).is_valid())

    def test_nif_valido_se_accepta_y_normaliza(self):
        form = RestauranteForm(self._payload(nif="  900123456-1  "))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["nif"], "900123456-1")

    def test_telefonos_identicos_se_rechazan(self):
        form = RestauranteForm(
            self._payload(telefono="+57 604 1234567", telefono_secundario="+57 604 1234567")
        )
        self.assertFalse(form.is_valid())

    def test_campos_criticos_son_obligatorios(self):
        form = RestauranteForm(self._payload(nif="", email=""))
        self.assertFalse(form.is_valid())
        self.assertIn("nif", form.errors)
        self.assertIn("email", form.errors)

    def test_sucursal_telefono_invalido_se_rechaza(self):
        restaurante = Restaurante.objects.create(
            nombre="Prueba", nif="901", email="a@b.co", direccion="x"
        )
        form = SucursalForm(
            {
                "restaurante": restaurante.pk,
                "nombre": "Centro",
                "direccion": "x",
                "telefono": "123",
                "activo": True,
            }
        )
        self.assertFalse(form.is_valid())

    def test_sucursal_telefono_valido_se_accepta(self):
        restaurante = Restaurante.objects.create(
            nombre="Prueba2", nif="902", email="a@b.co", direccion="x"
        )
        form = SucursalForm(
            {
                "restaurante": restaurante.pk,
                "nombre": "Centro",
                "direccion": "x",
                "telefono": "+57 604 1234567",
                "activo": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
