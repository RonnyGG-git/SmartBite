import threading
import time
from decimal import Decimal

from django.db import IntegrityError, connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from catalogo.models import Categoria, Producto
from cuentas.models import Rol, Usuario
from restaurantes.models import Restaurante, Sucursal

from .forms import CambiarEstadoOrdenForm
from .models import Cliente, DetalleOrden, Mesa, Orden


class TestBase(TestCase):
    """Datos de prueba comunes para todas las suites de operativo."""

    def setUp(self):
        self.restaurante = Restaurante.objects.create(
            nombre="Restaurante Test",
            nif="123456789",
            email="test@rest.com",
            direccion="Calle 1",
        )
        self.sucursal = Sucursal.objects.create(
            restaurante=self.restaurante,
            nombre="Sucursal Principal",
        )
        self.mesa = Mesa.objects.create(
            numero=1,
            sucursal=self.sucursal,
            estado=Mesa.DISPONIBLE,
            activa=True,
        )
        self.categoria = Categoria.objects.create(nombre="Bebidas")
        self.producto = Producto.objects.create(
            nombre="Gaseosa",
            precio=Decimal("5000.00"),
            categoria=self.categoria,
            sucursal=self.sucursal,
            disponible=True,
        )


class CambiarEstadoOrdenFormTests(TestBase):
    """Tests para T2: filtrado de choices de estado en CambiarEstadoOrdenForm."""

    def _crear_orden(self, estado=Orden.PENDIENTE):
        return Orden.objects.create(mesa=self.mesa, estado=estado)

    def _estados_disponibles(self, orden):
        form = CambiarEstadoOrdenForm(orden=orden)
        return [val for val, _ in form.fields["estado"].choices]

    # --- PENDIENTE ---

    def test_pendiente_muestra_en_preparacion_y_cancelada(self):
        orden = self._crear_orden(Orden.PENDIENTE)
        estados = self._estados_disponibles(orden)
        self.assertIn(Orden.EN_PREPARACION, estados)
        self.assertIn(Orden.CANCELADA, estados)
        self.assertEqual(len(estados), 2)

    def test_pendiente_no_muestra_lista(self):
        orden = self._crear_orden(Orden.PENDIENTE)
        estados = self._estados_disponibles(orden)
        self.assertNotIn(Orden.LISTA, estados)

    def test_pendiente_no_muestra_entregada(self):
        orden = self._crear_orden(Orden.PENDIENTE)
        estados = self._estados_disponibles(orden)
        self.assertNotIn(Orden.ENTREGADA, estados)

    def test_pendiente_no_muestra_pendiente(self):
        orden = self._crear_orden(Orden.PENDIENTE)
        estados = self._estados_disponibles(orden)
        self.assertNotIn(Orden.PENDIENTE, estados)

    # --- EN_PREPARACION ---

    def test_en_preparacion_muestra_lista_y_cancelada(self):
        orden = self._crear_orden(Orden.EN_PREPARACION)
        estados = self._estados_disponibles(orden)
        self.assertIn(Orden.LISTA, estados)
        self.assertIn(Orden.CANCELADA, estados)
        self.assertEqual(len(estados), 2)

    def test_en_preparacion_no_muestra_pendiente(self):
        orden = self._crear_orden(Orden.EN_PREPARACION)
        estados = self._estados_disponibles(orden)
        self.assertNotIn(Orden.PENDIENTE, estados)

    def test_en_preparacion_no_muestra_entregada(self):
        orden = self._crear_orden(Orden.EN_PREPARACION)
        estados = self._estados_disponibles(orden)
        self.assertNotIn(Orden.ENTREGADA, estados)

    # --- LISTA ---

    def test_lista_muestra_entregada_y_cancelada(self):
        orden = self._crear_orden(Orden.LISTA)
        estados = self._estados_disponibles(orden)
        self.assertIn(Orden.ENTREGADA, estados)
        self.assertIn(Orden.CANCELADA, estados)
        self.assertEqual(len(estados), 2)

    def test_lista_no_muestra_pendiente(self):
        orden = self._crear_orden(Orden.LISTA)
        estados = self._estados_disponibles(orden)
        self.assertNotIn(Orden.PENDIENTE, estados)

    def test_lista_no_muestra_en_preparacion(self):
        orden = self._crear_orden(Orden.LISTA)
        estados = self._estados_disponibles(orden)
        self.assertNotIn(Orden.EN_PREPARACION, estados)

    # --- ENTREGADA (terminal) ---

    def test_entregada_no_muestra_ningun_estado(self):
        orden = self._crear_orden(Orden.ENTREGADA)
        estados = self._estados_disponibles(orden)
        self.assertEqual(len(estados), 0)

    # --- CANCELADA (terminal) ---

    def test_cancelada_no_muestra_ningun_estado(self):
        orden = self._crear_orden(Orden.CANCELADA)
        estados = self._estados_disponibles(orden)
        self.assertEqual(len(estados), 0)

    # --- Validacion de transicion invalida ---

    def test_transicion_invalida_rechazada(self):
        """Una transicion no permitida (EN_PREPARACION -> PENDIENTE) debe fallar la validacion."""
        orden = self._crear_orden(Orden.EN_PREPARACION)
        form = CambiarEstadoOrdenForm(
            data={"estado": Orden.PENDIENTE},
            orden=orden,
        )
        self.assertFalse(form.is_valid())

    def test_transicion_valida_aceptada(self):
        """Una transicion permitida (PENDIENTE -> EN_PREPARACION) debe pasar la validacion."""
        orden = self._crear_orden(Orden.PENDIENTE)
        form = CambiarEstadoOrdenForm(
            data={"estado": Orden.EN_PREPARACION},
            orden=orden,
        )
        self.assertTrue(form.is_valid())


class ClienteUnicidadTest(TestCase):
    """Tests para T1.2: unique_together en Cliente (H10)."""

    def test_clientes_misma_combinacion_lanza_integrity_error(self):
        """Crear dos Clientes con mismo nombre, telefono y email lanza IntegrityError."""
        Cliente.objects.create(
            nombre="Juan Perez",
            telefono="3001234567",
            email="juan@test.com",
        )
        with self.assertRaises(IntegrityError):
            Cliente.objects.create(
                nombre="Juan Perez",
                telefono="3001234567",
                email="juan@test.com",
            )

    def test_clientes_mismo_nombre_distinto_telefono_no_error(self):
        """Dos Clientes con mismo nombre pero distinto telefono no deben fallar."""
        Cliente.objects.create(
            nombre="Juan Perez",
            telefono="3001234567",
            email="juan@test.com",
        )
        cliente2 = Cliente.objects.create(
            nombre="Juan Perez",
            telefono="3009999999",
            email="otro@test.com",
        )
        self.assertIsNotNone(cliente2.pk)

    def test_clientes_mismo_nombre_distinto_email_no_error(self):
        """Dos Clientes con mismo nombre pero distinto email no deben fallar."""
        Cliente.objects.create(
            nombre="Maria Lopez",
            telefono="3001234567",
            email="maria@test.com",
        )
        cliente2 = Cliente.objects.create(
            nombre="Maria Lopez",
            telefono="3001234567",
            email="otra@test.com",
        )
        self.assertIsNotNone(cliente2.pk)


class DetalleOrdenTimestampedTest(TestCase):
    """Tests para T1.3: DetalleOrden hereda de TimestampedModel (G10)."""

    def setUp(self):
        self.restaurante = Restaurante.objects.create(
            nombre="Restaurante Test",
            nif="123456789",
            email="test@rest.com",
            direccion="Calle 1",
        )
        self.sucursal = Sucursal.objects.create(
            restaurante=self.restaurante,
            nombre="Sucursal Principal",
        )
        self.mesa = Mesa.objects.create(
            numero=1,
            sucursal=self.sucursal,
            estado=Mesa.DISPONIBLE,
            activa=True,
        )
        self.orden = Orden.objects.create(mesa=self.mesa, estado=Orden.PENDIENTE)
        self.categoria = Categoria.objects.create(nombre="Bebidas")
        self.producto = Producto.objects.create(
            nombre="Gaseosa",
            precio=Decimal("5000.00"),
            categoria=self.categoria,
            sucursal=self.sucursal,
            disponible=True,
        )

    def test_detalle_tiene_campo_creado_en(self):
        """DetalleOrden debe tener campo creado_en (auto_now_add)."""
        detalle = DetalleOrden.objects.create(
            orden=self.orden,
            producto=self.producto,
            cantidad=2,
            precio_unitario=self.producto.precio,
        )
        self.assertIsNotNone(detalle.creado_en)

    def test_detalle_tiene_campo_actualizado_en(self):
        """DetalleOrden debe tener campo actualizado_en (auto_now)."""
        detalle = DetalleOrden.objects.create(
            orden=self.orden,
            producto=self.producto,
            cantidad=2,
            precio_unitario=self.producto.precio,
        )
        self.assertIsNotNone(detalle.actualizado_en)

    def test_actualizado_en_se_actualiza_al_guardar(self):
        """actualizado_en debe cambiar al modificar el registro."""
        detalle = DetalleOrden.objects.create(
            orden=self.orden,
            producto=self.producto,
            cantidad=2,
            precio_unitario=self.producto.precio,
        )
        original = detalle.actualizado_en
        # Pausa para garantizar una diferencia de tiempo real entre create() y
        # save(): en Windows la resolucion del reloj (~1 ms) puede hacer que
        # ambos guardados caigan en el mismo milisegundo y auto_now repita el
        # mismo valor de actualizado_en.
        time.sleep(0.05)
        detalle.cantidad = 3
        detalle.save()
        detalle.refresh_from_db()
        self.assertGreater(detalle.actualizado_en, original)

    def test_creado_en_no_cambia_al_guardar(self):
        """creado_en no debe cambiar al modificar el registro."""
        detalle = DetalleOrden.objects.create(
            orden=self.orden,
            producto=self.producto,
            cantidad=2,
            precio_unitario=self.producto.precio,
        )
        original = detalle.creado_en
        detalle.cantidad = 3
        detalle.save()
        detalle.refresh_from_db()
        self.assertEqual(detalle.creado_en, original)


class GenerarQrAuthTest(TestBase):
    """Tests para T3.1: proteger generar_qr con autenticacion (RF-009, H3)."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.url_qr = reverse("operativo:generar_qr", kwargs={"mesa_id": self.mesa.pk})

    def _crear_usuario(self, email, nombre, rol_nombre):
        rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
        return Usuario.objects.create_user(
            email=email,
            nombre=nombre,
            password="testpass123",
            rol=rol,
        )

    def test_generar_qr_sin_autenticacion_redirige_a_login(self):
        """Un usuario sin sesion que accede a generar_qr es redirigido al login."""
        respuesta = self.client.get(self.url_qr)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url_qr}",
            fetch_redirect_response=False,
        )

    def test_generar_qr_rol_no_autorizado_recibe_403(self):
        """Un usuario autenticado con rol no permitido (CAJERO) recibe 403."""
        self._crear_usuario("cajero.qr@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.qr@test.com", password="testpass123")
        respuesta = self.client.get(self.url_qr)
        self.assertEqual(respuesta.status_code, 403)

    def test_generar_qr_mesero_accede(self):
        """Un MESERO autenticado puede acceder a generar_qr."""
        self._crear_usuario("mesero.qr@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.qr@test.com", password="testpass123")
        respuesta = self.client.get(self.url_qr)
        self.assertEqual(respuesta.status_code, 200)

    def test_generar_qr_administrador_accede(self):
        """Un ADMINISTRADOR autenticado puede acceder a generar_qr."""
        self._crear_usuario("admin.qr@test.com", "Admin Test", "ADMINISTRADOR")
        self.client.login(email="admin.qr@test.com", password="testpass123")
        respuesta = self.client.get(self.url_qr)
        self.assertEqual(respuesta.status_code, 200)


class CrearClienteRapidoAuthTest(TestBase):
    """Tests para T3.2: proteger crear_cliente_rapido (RF-009, H4)."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.url = reverse("operativo:crear_cliente_rapido")
        self.datos_cliente = {
            "nombre": "Cliente Rapido",
            "telefono": "3001112233",
            "email": "rapido@test.com",
        }

    def _crear_usuario(self, email, nombre, rol_nombre):
        rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
        return Usuario.objects.create_user(
            email=email,
            nombre=nombre,
            password="testpass123",
            rol=rol,
        )

    def test_crear_cliente_rapido_sin_autenticacion_redirige_a_login(self):
        """Un usuario sin sesion que hace POST recibe 302 al login y no crea el cliente."""
        respuesta = self.client.post(self.url, self.datos_cliente)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertFalse(Cliente.objects.filter(nombre="Cliente Rapido").exists())

    def test_crear_cliente_rapido_rol_no_autorizado_recibe_403(self):
        """Un usuario autenticado con rol no permitido (CAJERO) recibe 403."""
        self._crear_usuario("cajero.cliente@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.cliente@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_cliente)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Cliente.objects.filter(nombre="Cliente Rapido").exists())

    def test_crear_cliente_rapido_mesero_crea_cliente_y_redirige(self):
        """Un MESERO autenticado crea el cliente y es redirigido a crear_orden."""
        self._crear_usuario("mesero.cliente@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.cliente@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_cliente)
        self.assertRedirects(
            respuesta,
            reverse("operativo:crear_orden"),
            fetch_redirect_response=False,
        )
        self.assertTrue(Cliente.objects.filter(nombre="Cliente Rapido").exists())

    def test_crear_cliente_rapido_administrador_accede(self):
        """Un ADMINISTRADOR autenticado crea el cliente y es redirigido a crear_orden."""
        self._crear_usuario("admin.cliente@test.com", "Admin Test", "ADMINISTRADOR")
        self.client.login(email="admin.cliente@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_cliente)
        self.assertRedirects(
            respuesta,
            reverse("operativo:crear_orden"),
            fetch_redirect_response=False,
        )
        self.assertTrue(Cliente.objects.filter(nombre="Cliente Rapido").exists())

    def test_crear_cliente_rapido_redirect_ignora_http_referer(self):
        """El redirect posterior al POST siempre apunta a crear_orden, sin usar HTTP_REFERER."""
        self._crear_usuario("mesero.referer@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.referer@test.com", password="testpass123")
        respuesta = self.client.post(
            self.url,
            self.datos_cliente,
            HTTP_REFERER="https://evil.example.com/phish",
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], reverse("operativo:crear_orden"))


class AgregarProductoAuthTest(TestBase):
    """Tests para T3.3: proteger agregar_producto con autenticacion (RF-009)."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.orden = Orden.objects.create(mesa=self.mesa, estado=Orden.PENDIENTE)
        self.url = reverse("operativo:agregar_producto", kwargs={"pk": self.orden.pk})
        self.datos_producto = {"producto": self.producto.pk, "cantidad": 2}

    def _crear_usuario(self, email, nombre, rol_nombre):
        rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
        return Usuario.objects.create_user(
            email=email,
            nombre=nombre,
            password="testpass123",
            rol=rol,
        )

    def test_agregar_producto_sin_autenticacion_redirige_a_login(self):
        """Un usuario sin sesion que hace POST recibe 302 al login y no agrega el producto."""
        respuesta = self.client.post(self.url, self.datos_producto)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertEqual(DetalleOrden.objects.count(), 0)

    def test_agregar_producto_rol_no_autorizado_recibe_403(self):
        """Un usuario autenticado con rol no permitido (CAJERO) recibe 403."""
        self._crear_usuario("cajero.producto@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.producto@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_producto)
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(DetalleOrden.objects.count(), 0)

    def test_agregar_producto_mesero_agrega_producto(self):
        """Un MESERO autenticado agrega el producto y es redirigido al detalle."""
        self._crear_usuario("mesero.producto@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.producto@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_producto)
        self.assertRedirects(
            respuesta,
            reverse("operativo:detalle_orden", kwargs={"pk": self.orden.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(DetalleOrden.objects.count(), 1)
        detalle = DetalleOrden.objects.get()
        self.assertEqual(detalle.orden, self.orden)
        self.assertEqual(detalle.producto, self.producto)
        self.assertEqual(detalle.cantidad, 2)

    def test_agregar_producto_administrador_agrega_producto(self):
        """Un ADMINISTRADOR autenticado agrega el producto y es redirigido al detalle."""
        self._crear_usuario("admin.producto@test.com", "Admin Test", "ADMINISTRADOR")
        self.client.login(email="admin.producto@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_producto)
        self.assertRedirects(
            respuesta,
            reverse("operativo:detalle_orden", kwargs={"pk": self.orden.pk}),
            fetch_redirect_response=False,
        )
        self.assertEqual(DetalleOrden.objects.count(), 1)


class CambiarEstadoOrdenAuthTest(TestBase):
    """Tests para T3.4: proteger cambiar_estado_orden con autenticacion (RF-009)."""

    def setUp(self):
        super().setUp()
        self.client = Client()
        self.orden = Orden.objects.create(mesa=self.mesa, estado=Orden.PENDIENTE)
        self.url = reverse("operativo:cambiar_estado_orden", kwargs={"pk": self.orden.pk})
        self.datos_estado = {"estado": Orden.EN_PREPARACION}

    def _crear_usuario(self, email, nombre, rol_nombre):
        rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
        return Usuario.objects.create_user(
            email=email,
            nombre=nombre,
            password="testpass123",
            rol=rol,
        )

    def test_cambiar_estado_sin_autenticacion_redirige_a_login(self):
        """Un usuario sin sesion que hace POST recibe 302 al login y el estado no cambia."""
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_cambiar_estado_rol_no_autorizado_recibe_403(self):
        """Un usuario autenticado con rol no permitido (CAJERO) recibe 403."""
        self._crear_usuario("cajero.estado@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.estado@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertEqual(respuesta.status_code, 403)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_cambiar_estado_mesero_cambia_estado(self):
        """Un MESERO autenticado cambia PENDIENTE a EN_PREPARACION y es redirigido al detalle."""
        self._crear_usuario("mesero.estado@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.estado@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertRedirects(
            respuesta,
            reverse("operativo:detalle_orden", kwargs={"pk": self.orden.pk}),
            fetch_redirect_response=False,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.EN_PREPARACION)

    def test_cambiar_estado_administrador_cambia_estado(self):
        """Un ADMINISTRADOR autenticado cambia PENDIENTE a EN_PREPARACION y es redirigido al detalle."""
        self._crear_usuario("admin.estado@test.com", "Admin Test", "ADMINISTRADOR")
        self.client.login(email="admin.estado@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertRedirects(
            respuesta,
            reverse("operativo:detalle_orden", kwargs={"pk": self.orden.pk}),
            fetch_redirect_response=False,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.EN_PREPARACION)


class CrearOrdenTest(TestBase):
    """Tests para T4.1: proteger creacion de orden contra concurrencia (RF-001, RF-010, H5)."""

    def setUp(self):
        super().setUp()
        self.url = reverse("operativo:crear_orden")
        rol, _ = Rol.objects.get_or_create(nombre="MESERO")
        self.usuario_mesero = Usuario.objects.create_user(
            email="mesero.orden@test.com",
            nombre="Mesero Test",
            password="testpass123",
            rol=rol,
        )
        self.datos_orden = {"mesa": self.mesa.pk}

    def test_crear_orden_mesa_disponible_funciona(self):
        """(a) Crear una orden para una mesa DISPONIBLE sigue funcionando: PENDIENTE + mesa OCUPADA."""
        self.client.login(email="mesero.orden@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_orden)
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Orden.objects.count(), 1)
        orden = Orden.objects.get()
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.assertEqual(orden.mesa, self.mesa)
        self.assertEqual(
            respuesta["Location"],
            reverse("operativo:detalle_orden", kwargs={"pk": orden.pk}),
        )
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.OCUPADA)

    def test_crear_orden_mesa_con_orden_activa_rechazada(self):
        """(b) Si la mesa ya tiene una orden activa, la segunda creacion se rechaza con error.

        Se crea la orden activa directamente con la mesa en DISPONIBLE para
        recrear exactamente el estado que la guarda `orden_activa` debe
        detectar (estado de carrera de dos solicitudes simultaneas).
        """
        Orden.objects.create(mesa=self.mesa, estado=Orden.PENDIENTE)
        self.client.login(email="mesero.orden@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_orden)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Esta mesa ya tiene una orden activa.")
        self.assertEqual(Orden.objects.filter(mesa=self.mesa).count(), 1)
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)


class CrearOrdenConcurrenciaTest(TransactionTestCase):
    """Tests para T4.1: concurrencia real en la creacion de orden (RF-010, H5).

    Se usa TransactionTestCase (y no TestCase) porque TestCase envuelve cada
    test en una transaccion y oculta los bloqueos reales de la base de datos;
    aqui los datos de setUp quedan commiteados y dos hilos compiten de verdad.

    Patron de concurrencia:
    - Dos hilos con threading.Barrier para sincronizar el POST simultaneo.
    - Cada hilo crea su propio Client (ya logueado desde el hilo principal,
      para no escribir sesiones en paralelo).
    - Cada hilo cierra sus conexiones de BD al terminar con
      connections.close_all(), porque cada hilo crea su propia conexion.

    Los Client se crean con raise_request_exception=False. Motivo: la senal
    global got_request_exception se dispara en el hilo que falla y ejecuta el
    store_exc_info de TODOS los Client conectados a la vez, por lo que el
    Client del hilo ganador almacenaria la excepcion del perdedor y su
    check_exception la relanzaria sobre un POST que ya hizo commit y devolvio
    302, clasificandolo incorrectamente como error. Con la bandera en False
    cada respuesta se clasifica solo por su status code, que si es confiable:
      302 -> creo la orden (redirect a detalle).
      200 -> rechazada (mesa ya con orden activa, o invalida si la mesa
             quedo OCUPADA por el ganador antes de validar el form).
      500 -> fallo de base de datos durante la peticion (bloqueo de SQLite).

    Limitacion conocida: SQLite ignora select_for_update() (es un no-op) y,
    en el modo cache compartido en memoria de los tests, usa bloqueo a nivel
    de tabla: dos hilos que escriben la misma tabla a la vez reciben
    'database table is locked' (el busy-handler no se invoca para
    SQLITE_LOCKED). Por eso el test es de doble camino: (1) si al menos un
    hilo tuvo exito (302), exige el criterio completo — exactamente una orden
    creada, la otra solicitud rechazada (200) o con error de BD (500); (2)
    si ambos recibieron el bloqueo de SQLite (500), exige la invariante
    RF-010 — nunca mas de una orden, ningun estado parcial — y deja el
    resultado documentado. El caso funcional secuencial esta cubierto por
    CrearOrdenTest.
    """

    def setUp(self):
        self.restaurante = Restaurante.objects.create(
            nombre="Restaurante Test",
            nif="123456789",
            email="test@rest.com",
            direccion="Calle 1",
        )
        self.sucursal = Sucursal.objects.create(
            restaurante=self.restaurante,
            nombre="Sucursal Principal",
        )
        self.mesa = Mesa.objects.create(
            numero=1,
            sucursal=self.sucursal,
            estado=Mesa.DISPONIBLE,
            activa=True,
        )
        rol, _ = Rol.objects.get_or_create(nombre="MESERO")
        self.usuario_mesero = Usuario.objects.create_user(
            email="mesero.concurrencia@test.com",
            nombre="Mesero Test",
            password="testpass123",
            rol=rol,
        )
        self.url = reverse("operativo:crear_orden")
        self.datos_orden = {"mesa": self.mesa.pk}

    def test_dos_solicitudes_simultaneas_solo_crean_una_orden(self):
        """Dos POST simultaneos para la misma mesa: solo una orden exitosa, la otra recibe error."""
        clientes = []
        for _ in range(2):
            cliente = Client(raise_request_exception=False)
            autenticado = cliente.login(
                email="mesero.concurrencia@test.com", password="testpass123"
            )
            self.assertTrue(autenticado, "La sesion del hilo debe iniciar en el hilo principal")
            clientes.append(cliente)

        barrera = threading.Barrier(2, timeout=10)
        resultados = []

        def intentar(indice, cliente):
            try:
                barrera.wait()
                respuesta = cliente.post(self.url, self.datos_orden)
                codigo = respuesta.status_code
                if codigo == 302:
                    resultados.append(("creado", indice))
                elif codigo == 200:
                    resultados.append(("rechazado", indice))
                elif codigo == 500:
                    resultados.append(("error_bd", indice))
                else:
                    resultados.append((f"inesperado_{codigo}", indice))
            except Exception as exc:
                resultados.append(
                    ("excepcion_no_cubierta", f"[hilo {indice}] {type(exc).__name__}: {exc}")
                )
            finally:
                connections.close_all()

        hilos = [
            threading.Thread(target=intentar, args=(i, clientes[i]))
            for i in range(2)
        ]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=15)

        self.assertEqual(
            len(resultados),
            2,
            f"Ambos hilos deben concluir sin quedarse colgados: {resultados}",
        )
        self.assertEqual(
            [r[0] for r in resultados if r[0].startswith(("excepcion", "inesperado"))],
            [],
            f"Ninguna via inesperada debe propagarse al hilo: {resultados}",
        )

        creados = [r for r in resultados if r[0] == "creado"]
        total_ordenes = Orden.objects.filter(mesa=self.mesa).count()

        # RF-010: invariante absoluta en cualquier entorno: jamas dos ordenes.
        self.assertLessEqual(
            total_ordenes,
            1,
            f"RF-010: jamas debe existir mas de una orden para la misma mesa: {resultados}",
        )
        self.assertLessEqual(
            len(creados),
            1,
            f"RF-010: a lo sumo una solicitud puede crear la orden: {resultados}",
        )

        if creados:
            # Camino con una ganadora: exactamente una orden creada y la otra
            # solicitud rechazada (200) o con error de bloqueo (500).
            self.assertEqual(
                len(creados),
                1,
                f"Exactamente una solicitud debe crear la orden: {resultados}",
            )
            self.assertEqual(
                len(resultados) - 1,
                1,
                f"La otra solicitud no debe crear nada: {resultados}",
            )
            perdedor = next(r for r in resultados if r[0] != "creado")
            self.assertIn(
                perdedor[0],
                ("rechazado", "error_bd"),
                f"La otra solicitud debe ser 200 (orden activa) o 500 (bloqueo SQLite): {resultados}",
            )
            self.assertEqual(
                total_ordenes,
                1,
                "RF-010: exactamente una orden creada por la carrera",
            )
            self.mesa.refresh_from_db()
            self.assertEqual(self.mesa.estado, Mesa.OCUPADA)
        else:
            # Camino documentado de SQLite (ver docstring): al escribir a la
            # vez en la misma tabla del cache compartido, ambos hilos reciben
            # 'database table is locked' (500) y ninguno crea la orden.
            # RF-010 se cumple: no hubo ningun duplicado ni estado parcial.
            for tipo, detalle in resultados:
                self.assertEqual(
                    tipo,
                    "error_bd",
                    f"Sin exitos, ambos hilos deben recibir 500 por el bloqueo de SQLite: {resultados}",
                )
            self.assertEqual(
                total_ordenes,
                0,
                "Ningun hilo completo la creacion: no debe quedar orden parcial: "
                f"resultados={resultados}, "
                f"mesa={self.mesa.estado}, "
                f"ordenes={list(Orden.objects.values('pk', 'estado', 'mesa_id', 'creado_en'))}",
            )
            self.mesa.refresh_from_db()
            self.assertEqual(
                self.mesa.estado,
                Mesa.DISPONIBLE,
                "La mesa no debe quedar OCUPADA si nadie creo la orden",
            )
