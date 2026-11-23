import io
from datetime import timedelta
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from cliente.models import Retroalimentacion
from core.testing import crear_escenario, crear_usuario
from cuentas.models import Rol, Usuario
from inventario.models import Compra, ItemInventario, MovimientoInventario, Proveedor
from operativo.models import Mesa, Orden, Reserva
from restaurantes.models import Restaurante, Sucursal


def api_de(usuario):
    cliente = APIClient()
    token, _ = Token.objects.get_or_create(user=usuario)
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return cliente


class GestionTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.admin = crear_usuario("ADMINISTRADOR", email="admin@t.co")
        self.d["restaurante"].administrador = self.admin
        self.d["restaurante"].save()
        self.api = api_de(self.admin)
        self.inventario = api_de(crear_usuario("JEFE_INVENTARIO", email="inv@t.co"))
        self.otro = Restaurante.objects.create(nombre="Otro", nif="77", email="o@o.co", direccion="x")
        self.sucursal_ajena = Sucursal.objects.create(restaurante=self.otro, nombre="Ajena")

    def item(self, **datos):
        base = {"nombre": "Papa", "unidad_medida": "kg", "stock_actual": 5, "stock_minimo": 10,
                "costo_unitario": "1200", "sucursal": self.d["centro"].pk}
        base.update(datos)
        return self.inventario.post(reverse("api:g-items-list"), base, format="json")

    def test_item_se_crea_con_las_reglas_del_formulario_web(self):
        r = self.item()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["stock_bajo"])
        r = self.item(nombre="Ajeno", sucursal=self.sucursal_ajena.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn("sucursal", r.json()["errores"])

    def test_ajustar_stock_registra_movimiento(self):
        item = ItemInventario.objects.create(nombre="Arroz", sucursal=self.d["centro"], stock_actual=10)
        r = self.inventario.post(reverse("api:g-items-ajustar", args=[item.pk]), {"tipo": "SALIDA", "cantidad": 4, "motivo": "Merma"}, format="json")
        self.assertEqual(r.json()["stock_actual"], 6)
        self.assertEqual(MovimientoInventario.objects.get().tipo, "SALIDA")
        r = self.inventario.post(reverse("api:g-items-ajustar", args=[item.pk]), {"tipo": "SALIDA", "cantidad": 0, "motivo": "x"}, format="json")
        self.assertIn("cantidad", r.json()["errores"])

    def test_editar_conserva_los_campos_que_no_se_envian(self):
        item = ItemInventario.objects.create(nombre="Sal", sucursal=self.d["centro"], stock_actual=3, costo_unitario=Decimal("500"))
        r = self.inventario.put(reverse("api:g-items-detail", args=[item.pk]), {"stock_minimo": 2}, format="json")
        self.assertEqual(r.status_code, 200)
        item.refresh_from_db()
        self.assertEqual((item.nombre, item.stock_minimo), ("Sal", 2))

    def test_proveedor_queda_en_el_restaurante_actual_y_compra_se_recibe(self):
        r = self.inventario.post(reverse("api:g-proveedores-list"), {"nombre": "Fruver", "activo": True}, format="json")
        proveedor = Proveedor.objects.get(pk=r.json()["id"])
        self.assertEqual(proveedor.restaurante, self.d["restaurante"])
        item = ItemInventario.objects.create(nombre="Tomate", sucursal=self.d["centro"], stock_actual=1)
        r = self.inventario.post(reverse("api:g-compras-list"), {"proveedor": proveedor.pk, "detalles": [
            {"item": item.pk, "cantidad": 4, "costo_unitario": "900"}]}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["total"], "3600.00")
        compra = r.json()["id"]
        r = self.inventario.post(reverse("api:g-compras-recibir", args=[compra]))
        self.assertEqual(r.json()["estado"], Compra.RECIBIDA)
        item.refresh_from_db()
        self.assertEqual(item.stock_actual, 5)
        self.assertEqual(MovimientoInventario.objects.get().motivo, f"Recepción compra #{compra}")
        self.assertEqual(self.inventario.post(reverse("api:g-compras-anular", args=[compra])).json()["code"], "compra_no_pendiente")

    def test_compra_con_item_ajeno_no_se_crea(self):
        proveedor = Proveedor.objects.create(nombre="P", restaurante=self.d["restaurante"])
        ajeno = ItemInventario.objects.create(nombre="X", sucursal=self.sucursal_ajena)
        r = self.inventario.post(reverse("api:g-compras-list"), {"proveedor": proveedor.pk, "detalles": [
            {"item": ajeno.pk, "cantidad": 1, "costo_unitario": "1"}]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Compra.objects.count(), 0)

    def test_categoria_repetida_se_rechaza_y_producto_cambia_disponibilidad_y_foto(self):
        r = self.api.post(reverse("api:g-categorias-list"), {"nombre": "Platos fuertes"}, format="json")
        self.assertEqual(r.status_code, 400)
        producto = self.d["bandeja"]
        r = self.api.post(reverse("api:g-productos-disponibilidad", args=[producto.pk]))
        self.assertFalse(r.json()["disponible"])
        archivo = io.BytesIO()
        Image.new("RGB", (1200, 800), "orange").save(archivo, "JPEG")
        subida = SimpleUploadedFile("f.jpg", archivo.getvalue(), "image/jpeg")
        r = self.api.post(reverse("api:g-productos-foto", args=[producto.pk]), {"archivo": subida}, format="multipart")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/imagen/", r.json()["imagen"])
        self.assertEqual(self.api.delete(reverse("api:g-productos-foto", args=[producto.pk])).json()["imagen"], "")

    def test_mesa_qr_y_mesa_con_ordenes_no_se_borra(self):
        mesa = self.d["mesa"]
        r = self.api.get(reverse("api:g-mesas-qr", args=[mesa.pk]))
        self.assertIn("/cliente/mesa/%d/" % mesa.pk, r.json()["url"])
        Orden.objects.create(mesa=mesa, sucursal=self.d["centro"])
        self.assertEqual(self.api.delete(reverse("api:g-mesas-detail", args=[mesa.pk])).json()["code"], "en_uso")
        mesero = api_de(crear_usuario("MESERO", email="m@t.co"))
        self.assertEqual(mesero.post(reverse("api:g-mesas-list"), {}, format="json").status_code, 403)

    def test_restaurante_nuevo_queda_del_admin_y_regenera_codigo(self):
        r = self.api.post(reverse("api:g-restaurantes-list"), {
            "nombre": "Nuevo", "nif": "900111", "email": "n@n.co", "direccion": "Calle 1",
            "telefono": "3001234567", "activo": True}, format="json")
        self.assertEqual(r.status_code, 201, r.json())
        nuevo = Restaurante.objects.get(pk=r.json()["id"])
        self.assertEqual(nuevo.administrador, self.admin)
        antes = nuevo.codigo_acceso
        self.assertNotEqual(self.api.post(reverse("api:g-restaurantes-codigo", args=[nuevo.pk])).json()["codigo_acceso"], antes)
        self.assertNotIn(self.otro.pk, [x["id"] for x in self.api.get(reverse("api:g-restaurantes-list")).json()])

    def test_usuarios_crear_no_desactivarse_y_roles_de_empleado(self):
        Rol.objects.get_or_create(nombre="MESERO")
        roles = self.api.get(reverse("api:g-usuarios-roles")).json()
        mesero = next(x for x in roles if x["nombre"] == "MESERO")
        self.assertNotIn("CLIENTE", [x["nombre"] for x in roles])
        r = self.api.post(reverse("api:g-usuarios-list"), {
            "nombre": "Nuevo Mesero", "email": "nuevo@t.co", "rol": mesero["id"], "sucursal": self.d["centro"].pk,
            "password1": "Clave-Segura-2026", "password2": "Clave-Segura-2026"}, format="json")
        self.assertEqual(r.status_code, 201, r.json())
        self.assertEqual(Usuario.objects.get(email="nuevo@t.co").restaurante, self.d["restaurante"])
        self.assertEqual(self.api.post(reverse("api:g-usuarios-activo", args=[self.admin.pk])).json()["code"], "propia_cuenta")
        self.assertFalse(self.api.post(reverse("api:g-usuarios-activo", args=[r.json()["id"]])).json()["is_active"])

    def test_dashboard_y_opiniones(self):
        Retroalimentacion.objects.create(mensaje="Muy rico", mesa=self.d["mesa"])
        tablero = self.api.get(reverse("api:g_dashboard")).json()
        self.assertEqual(tablero["total_mesas"], 1)
        self.assertEqual(len(tablero["ordenes_por_estado"]), 6)
        opinion = self.api.get(reverse("api:g-opiniones-list")).json()["results"][0]
        self.assertTrue(self.api.post(reverse("api:g-opiniones-revisar", args=[opinion["id"]])).json()["revisada"])
        self.assertEqual(self.inventario.get(reverse("api:g_dashboard")).status_code, 403)


class ClientePublicoExtraTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        Mesa.objects.filter(pk=self.d["mesa"].pk).update(capacidad=4)
        self.api = APIClient()

    def reservar(self, personas):
        cuando = timezone.localtime() + timedelta(days=2)
        return self.api.post(reverse("api:reservar", args=[self.d["centro"].pk]), {
            "fecha": cuando.date().isoformat(), "hora": "19:00", "num_personas": personas,
            "nombre": "Luis", "telefono": "3001112233"}, format="json")

    def test_reservar_ver_y_cancelar(self):
        r = self.reservar(2)
        self.assertEqual(r.status_code, 201, r.json())
        codigo = r.json()["codigo"]
        self.assertEqual(self.api.get(reverse("api:reserva_publica", args=[codigo.lower()])).json()["estado"], Reserva.CONFIRMADA)
        self.assertEqual(self.api.post(reverse("api:reserva_publica", args=[codigo])).json()["estado"], Reserva.CANCELADA)

    def test_reserva_sin_capacidad_explica_el_motivo(self):
        r = self.reservar(20)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "capacidad")

    def test_opinar_con_mesa(self):
        r = self.api.post(reverse("api:opinar"), {"tipo": "SUGERENCIA", "mensaje": "Más ají", "mesa": self.d["mesa"].pk}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Retroalimentacion.objects.get().mesa, self.d["mesa"])
