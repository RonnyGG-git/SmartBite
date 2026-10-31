from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalogo.models import Categoria, Producto
from cuentas.models import Rol, Usuario
from inventario.models import ItemInventario
from operativo.models import Mesa, Orden
from restaurantes.models import Restaurante, Sucursal

CLAVE = "Clave-Segura-2026!"


class MultiRestauranteTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        for nombre in ("ADMINISTRADOR", "MESERO", "JEFE_COCINA", "CAJERO", "JEFE_INVENTARIO"):
            Rol.objects.create(nombre=nombre)
        cls.a = cls.crear_negocio("a", "900111111-1")
        cls.b = cls.crear_negocio("b", "900222222-2")

    @classmethod
    def crear_negocio(cls, sufijo, nif):
        admin = Usuario.objects.create_user(
            f"admin.{sufijo}@test.co", f"Admin {sufijo}", CLAVE, rol=Rol.objects.get(nombre="ADMINISTRADOR")
        )
        restaurante = Restaurante.objects.create(
            nombre=f"Restaurante {sufijo}", nif=nif, email=f"{sufijo}@test.co", direccion="Calle 1",
            administrador=admin,
        )
        sucursal = Sucursal.objects.create(restaurante=restaurante, nombre=f"Centro {sufijo}")
        categoria = Categoria.objects.create(nombre="Bebidas", restaurante=restaurante)
        return {
            "admin": admin,
            "restaurante": restaurante,
            "sucursal": sucursal,
            "categoria": categoria,
            "mesa": Mesa.objects.create(numero=1, sucursal=sucursal),
            "producto": Producto.objects.create(
                nombre=f"Jugo {sufijo}", precio=Decimal("5000"), categoria=categoria, sucursal=sucursal
            ),
            "item": ItemInventario.objects.create(nombre=f"Naranja {sufijo}", stock_actual=5, sucursal=sucursal),
            "mesero": Usuario.objects.create_user(
                f"mesero.{sufijo}@test.co", f"Mesero {sufijo}", CLAVE,
                rol=Rol.objects.get(nombre="MESERO"), restaurante=restaurante,
            ),
        }


class RestaurantesDelAdministradorTests(MultiRestauranteTestCase):

    def test_cu_adm_09_cada_admin_ve_solo_sus_restaurantes(self):
        self.client.force_login(self.a["admin"])
        lista = self.client.get(reverse("restaurantes:restaurantes_list")).context["restaurantes"]
        self.assertEqual(list(lista), [self.a["restaurante"]])
        editar_ajeno = reverse("restaurantes:restaurante_editar", args=[self.b["restaurante"].pk])
        self.assertEqual(self.client.get(editar_ajeno).status_code, 404)

    def test_cu_adm_09_el_restaurante_nuevo_es_de_quien_lo_crea(self):
        self.client.force_login(self.a["admin"])
        self.client.post(reverse("restaurantes:restaurante_crear"), {
            "nombre": "Sede Playa", "nif": "900333333-3", "email": "playa@test.co", "direccion": "Calle 9",
            "activo": "on",
        })
        nuevo = Restaurante.objects.get(nombre="Sede Playa")
        self.assertEqual(nuevo.administrador, self.a["admin"])
        mesas = self.client.get(reverse("operativo:mesas_list")).context["mesas"]
        self.assertEqual(list(mesas), [])

    def test_cu_adm_09_admin_con_varios_restaurantes_elige_con_cual_trabajar(self):
        otro = Restaurante.objects.create(
            nombre="Sede Norte", nif="900444444-4", email="n@test.co", direccion="x", administrador=self.a["admin"]
        )
        mesa_norte = Mesa.objects.create(numero=7, sucursal=Sucursal.objects.create(restaurante=otro, nombre="N"))
        self.client.force_login(self.a["admin"])
        self.assertEqual(list(self.client.get(reverse("operativo:mesas_list")).context["mesas"]), [self.a["mesa"]])
        self.client.post(reverse("restaurantes:seleccionar_restaurante", args=[otro.pk]))
        self.assertEqual(list(self.client.get(reverse("operativo:mesas_list")).context["mesas"]), [mesa_norte])
        respuesta = self.client.post(reverse("restaurantes:seleccionar_restaurante", args=[self.b["restaurante"].pk]))
        self.assertEqual(respuesta.status_code, 404)


class CodigoDeAccesoTests(MultiRestauranteTestCase):

    def registrar_empleado(self, codigo, email="nuevo@test.co"):
        return self.client.post(reverse("cuentas:registro_empleado"), {
            "codigo": codigo, "nombre": "Empleado Nuevo", "email": email,
            "password1": CLAVE, "password2": CLAVE,
        })

    def test_cu_adm_17_cada_restaurante_tiene_un_codigo_unico(self):
        codigo_a, codigo_b = self.a["restaurante"].codigo_acceso, self.b["restaurante"].codigo_acceso
        self.assertEqual(len(codigo_a), 8)
        self.assertNotEqual(codigo_a, codigo_b)

    def test_cu_adm_17_regenerar_invalida_el_codigo_anterior(self):
        anterior = self.a["restaurante"].codigo_acceso
        self.client.force_login(self.a["admin"])
        self.client.post(reverse("restaurantes:regenerar_codigo", args=[self.a["restaurante"].pk]))
        self.a["restaurante"].refresh_from_db()
        self.assertNotEqual(self.a["restaurante"].codigo_acceso, anterior)
        self.client.logout()
        self.registrar_empleado(anterior)
        self.assertFalse(Usuario.objects.filter(email="nuevo@test.co").exists())

    def test_cu_adm_17_no_se_regenera_el_codigo_de_otro(self):
        anterior = self.b["restaurante"].codigo_acceso
        self.client.force_login(self.a["admin"])
        self.client.post(reverse("restaurantes:regenerar_codigo", args=[self.b["restaurante"].pk]))
        self.b["restaurante"].refresh_from_db()
        self.assertEqual(self.b["restaurante"].codigo_acceso, anterior)

    def test_cu_adm_18_ingresar_al_restaurante_con_codigo(self):
        respuesta = self.registrar_empleado(self.a["restaurante"].codigo_acceso.lower())
        self.assertRedirects(respuesta, reverse("cuentas:pendiente"))
        empleado = Usuario.objects.get(email="nuevo@test.co")
        self.assertEqual((empleado.restaurante, empleado.rol), (self.a["restaurante"], None))
        self.assertEqual(self.client.get(reverse("operativo:mesas_list")).status_code, 403)

    def test_cu_adm_18_codigo_invalido(self):
        respuesta = self.registrar_empleado("NOEXISTE")
        self.assertContains(respuesta, "El código no es válido")
        self.assertFalse(Usuario.objects.filter(email="nuevo@test.co").exists())

    def test_cu_adm_18_el_admin_ve_al_empleado_nuevo_y_le_asigna_rol(self):
        self.registrar_empleado(self.a["restaurante"].codigo_acceso)
        empleado = Usuario.objects.get(email="nuevo@test.co")
        self.client.force_login(self.b["admin"])
        self.assertNotIn(empleado, list(self.client.get(reverse("cuentas:usuarios_list")).context["usuarios"]))
        self.client.force_login(self.a["admin"])
        self.assertIn(empleado, list(self.client.get(reverse("cuentas:usuarios_list")).context["usuarios"]))
        self.client.post(reverse("cuentas:usuario_editar", args=[empleado.pk]), {
            "nombre": empleado.nombre, "email": empleado.email,
            "rol": Rol.objects.get(nombre="CAJERO").pk, "sucursal": self.a["sucursal"].pk, "is_active": "on",
        })
        empleado.refresh_from_db()
        self.assertEqual(empleado.rol.nombre, "CAJERO")

    def test_el_admin_no_puede_crear_otros_administradores(self):
        self.client.force_login(self.a["admin"])
        form = self.client.get(reverse("cuentas:usuario_crear")).context["form"]
        self.assertNotIn("ADMINISTRADOR", [r.nombre for r in form.fields["rol"].queryset])

    def test_registro_publico_de_administrador(self):
        respuesta = self.client.post(reverse("cuentas:registro_admin"), {
            "nombre": "Dueña Nueva", "email": "duena@test.co", "password1": CLAVE, "password2": CLAVE,
        })
        self.assertRedirects(respuesta, reverse("restaurantes:restaurante_crear"))
        duena = Usuario.objects.get(email="duena@test.co")
        self.assertEqual(duena.rol.nombre, "ADMINISTRADOR")
        self.assertEqual(list(self.client.get(reverse("catalogo:productos_list")).context["productos"]), [])


class AislamientoDeDatosTests(MultiRestauranteTestCase):

    def test_productos_mesas_e_inventario_son_de_cada_restaurante(self):
        self.client.force_login(self.a["admin"])
        self.assertEqual(list(self.client.get(reverse("catalogo:productos_list")).context["productos"]), [self.a["producto"]])
        self.assertEqual(list(self.client.get(reverse("operativo:mesas_list")).context["mesas"]), [self.a["mesa"]])
        self.assertEqual(list(self.client.get(reverse("inventario:inventario_list")).context["items"]), [self.a["item"]])

    def test_no_se_abre_ni_se_modifica_lo_de_otro_restaurante(self):
        orden_b = Orden.objects.create(mesa=self.b["mesa"])
        self.client.force_login(self.a["mesero"])
        self.assertEqual(self.client.get(reverse("operativo:detalle_orden", args=[orden_b.pk])).status_code, 404)
        self.client.post(reverse("operativo:cambiar_estado_orden", args=[orden_b.pk]), {"estado": Orden.CANCELADA})
        orden_b.refresh_from_db()
        self.assertEqual(orden_b.estado, Orden.PENDIENTE)
        self.client.force_login(self.a["admin"])
        editar = reverse("catalogo:producto_editar", args=[self.b["producto"].pk])
        self.assertEqual(self.client.get(editar).status_code, 404)

    def test_los_formularios_no_ofrecen_datos_de_otro_restaurante(self):
        self.client.force_login(self.a["admin"])
        form = self.client.get(reverse("catalogo:producto_crear")).context["form"]
        self.assertEqual(list(form.fields["sucursal"].queryset), [self.a["sucursal"]])
        self.assertEqual(list(form.fields["categoria"].queryset), [self.a["categoria"]])
        self.client.post(reverse("operativo:mesa_crear"), {
            "numero": 9, "capacidad": 4, "sucursal": self.b["sucursal"].pk, "activa": "on",
        })
        self.assertFalse(Mesa.objects.filter(numero=9).exists())

    def test_misma_categoria_en_dos_restaurantes_pero_no_repetida_en_uno(self):
        self.assertEqual(Categoria.objects.filter(nombre="Bebidas").count(), 2)
        self.client.force_login(self.a["admin"])
        self.client.post(reverse("catalogo:categoria_crear"), {"nombre": "bebidas"})
        self.assertEqual(Categoria.objects.filter(restaurante=self.a["restaurante"]).count(), 1)
        self.client.post(reverse("catalogo:categoria_crear"), {"nombre": "Postres"})
        self.assertEqual(Categoria.objects.get(nombre="Postres").restaurante, self.a["restaurante"])

    def test_cocina_y_caja_solo_ven_ordenes_de_su_restaurante(self):
        orden_a = Orden.objects.create(mesa=self.a["mesa"])
        Orden.objects.create(mesa=self.b["mesa"])
        self.client.force_login(self.a["admin"])
        self.assertEqual(list(self.client.get(reverse("cocina:cocina")).context["ordenes"]), [orden_a])
        self.assertEqual(self.client.get(reverse("reportes:dashboard")).context["ordenes_hoy"], 1)

    def test_el_menu_del_qr_es_el_del_restaurante_de_la_mesa(self):
        self.client.get(reverse("cliente:mesa", args=[self.b["mesa"].pk]))
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": "PARA_LLEVAR"})
        respuesta = self.client.get(reverse("cliente:menu"))
        productos = [p for _, lista in respuesta.context["categorias"] for p in lista]
        self.assertEqual(productos, [self.b["producto"]])

    def test_roles_y_permisos_globales_solo_para_el_superusuario(self):
        self.client.force_login(self.a["admin"])
        self.assertEqual(self.client.get(reverse("cuentas:roles_list")).status_code, 403)
