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
    def _crear_orden(self, estado=Orden.PENDIENTE):
        return Orden.objects.create(mesa=self.mesa, estado=estado)

    def _estados_disponibles(self, orden):
        form = CambiarEstadoOrdenForm(orden=orden)
        return [val for val, _ in form.fields["estado"].choices]


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


    def test_entregada_no_muestra_ningun_estado(self):
        orden = self._crear_orden(Orden.ENTREGADA)
        estados = self._estados_disponibles(orden)
        self.assertEqual(len(estados), 0)


    def test_cancelada_no_muestra_ningun_estado(self):
        orden = self._crear_orden(Orden.CANCELADA)
        estados = self._estados_disponibles(orden)
        self.assertEqual(len(estados), 0)


    def test_transicion_invalida_rechazada(self):
        orden = self._crear_orden(Orden.EN_PREPARACION)
        form = CambiarEstadoOrdenForm(
            data={"estado": Orden.PENDIENTE},
            orden=orden,
        )
        self.assertFalse(form.is_valid())

    def test_transicion_valida_aceptada(self):
        orden = self._crear_orden(Orden.PENDIENTE)
        form = CambiarEstadoOrdenForm(
            data={"estado": Orden.EN_PREPARACION},
            orden=orden,
        )
        self.assertTrue(form.is_valid())


class ClienteUnicidadTest(TestCase):
    def test_clientes_misma_combinacion_lanza_integrity_error(self):
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
        detalle = DetalleOrden.objects.create(
            orden=self.orden,
            producto=self.producto,
            cantidad=2,
            precio_unitario=self.producto.precio,
        )
        self.assertIsNotNone(detalle.creado_en)

    def test_detalle_tiene_campo_actualizado_en(self):
        detalle = DetalleOrden.objects.create(
            orden=self.orden,
            producto=self.producto,
            cantidad=2,
            precio_unitario=self.producto.precio,
        )
        self.assertIsNotNone(detalle.actualizado_en)

    def test_actualizado_en_se_actualiza_al_guardar(self):
        detalle = DetalleOrden.objects.create(
            orden=self.orden,
            producto=self.producto,
            cantidad=2,
            precio_unitario=self.producto.precio,
        )
        original = detalle.actualizado_en
        time.sleep(0.05)
        detalle.cantidad = 3
        detalle.save()
        detalle.refresh_from_db()
        self.assertGreater(detalle.actualizado_en, original)

    def test_creado_en_no_cambia_al_guardar(self):
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
            restaurante=self.restaurante,
        )

    def test_generar_qr_sin_autenticacion_redirige_a_login(self):
        respuesta = self.client.get(self.url_qr)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url_qr}",
            fetch_redirect_response=False,
        )

    def test_generar_qr_rol_no_autorizado_recibe_403(self):
        self._crear_usuario("cajero.qr@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.qr@test.com", password="testpass123")
        respuesta = self.client.get(self.url_qr)
        self.assertEqual(respuesta.status_code, 403)

    def test_generar_qr_mesero_accede(self):
        self._crear_usuario("mesero.qr@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.qr@test.com", password="testpass123")
        respuesta = self.client.get(self.url_qr)
        self.assertEqual(respuesta.status_code, 200)

    def test_generar_qr_administrador_accede(self):
        self._crear_usuario("admin.qr@test.com", "Admin Test", "ADMINISTRADOR")
        self.client.login(email="admin.qr@test.com", password="testpass123")
        respuesta = self.client.get(self.url_qr)
        self.assertEqual(respuesta.status_code, 200)


class CrearClienteRapidoAuthTest(TestBase):
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
            restaurante=self.restaurante,
        )

    def test_crear_cliente_rapido_sin_autenticacion_redirige_a_login(self):
        respuesta = self.client.post(self.url, self.datos_cliente)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertFalse(Cliente.objects.filter(nombre="Cliente Rapido").exists())

    def test_crear_cliente_rapido_rol_no_autorizado_recibe_403(self):
        self._crear_usuario("cajero.cliente@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.cliente@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_cliente)
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Cliente.objects.filter(nombre="Cliente Rapido").exists())

    def test_crear_cliente_rapido_mesero_crea_cliente_y_redirige(self):
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
            restaurante=self.restaurante,
        )

    def test_agregar_producto_sin_autenticacion_redirige_a_login(self):
        respuesta = self.client.post(self.url, self.datos_producto)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.assertEqual(DetalleOrden.objects.count(), 0)

    def test_agregar_producto_rol_no_autorizado_recibe_403(self):
        self._crear_usuario("cajero.producto@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.producto@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_producto)
        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(DetalleOrden.objects.count(), 0)

    def test_agregar_producto_mesero_agrega_producto(self):
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
            restaurante=self.restaurante,
        )

    def test_cambiar_estado_sin_autenticacion_redirige_a_login(self):
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertRedirects(
            respuesta,
            f"{reverse('cuentas:login')}?next={self.url}",
            fetch_redirect_response=False,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_cambiar_estado_rol_no_autorizado_recibe_403(self):
        self._crear_usuario("cajero.estado@test.com", "Cajero Test", "CAJERO")
        self.client.login(email="cajero.estado@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertEqual(respuesta.status_code, 403)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_cambiar_estado_mesero_no_puede_iniciar_preparacion(self):
        self._crear_usuario("mesero.estado@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.estado@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertRedirects(
            respuesta,
            reverse("operativo:detalle_orden", kwargs={"pk": self.orden.pk}),
            fetch_redirect_response=False,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_cambiar_estado_administrador_tampoco_inicia_preparacion(self):
        self._crear_usuario("admin.estado@test.com", "Admin Test", "ADMINISTRADOR")
        self.client.login(email="admin.estado@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_estado)
        self.assertRedirects(
            respuesta,
            reverse("operativo:detalle_orden", kwargs={"pk": self.orden.pk}),
            fetch_redirect_response=False,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_cambiar_estado_mesero_si_puede_cancelar(self):
        self._crear_usuario("mesero.cancelar@test.com", "Mesero Test", "MESERO")
        self.client.login(email="mesero.cancelar@test.com", password="testpass123")
        respuesta = self.client.post(self.url, {"estado": Orden.CANCELADA})
        self.assertRedirects(
            respuesta,
            reverse("operativo:detalle_orden", kwargs={"pk": self.orden.pk}),
            fetch_redirect_response=False,
        )
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.CANCELADA)


class CrearOrdenTest(TestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("operativo:crear_orden")
        rol, _ = Rol.objects.get_or_create(nombre="MESERO")
        self.usuario_mesero = Usuario.objects.create_user(
            email="mesero.orden@test.com",
            nombre="Mesero Test",
            password="testpass123",
            rol=rol,
            restaurante=self.restaurante,
        )
        self.datos_orden = {"mesa": self.mesa.pk}

    def test_crear_orden_mesa_disponible_funciona(self):
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
        Orden.objects.create(mesa=self.mesa, estado=Orden.PENDIENTE)
        self.client.login(email="mesero.orden@test.com", password="testpass123")
        respuesta = self.client.post(self.url, self.datos_orden)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Esta mesa ya tiene una orden activa.")
        self.assertEqual(Orden.objects.filter(mesa=self.mesa).count(), 1)
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)


class CrearOrdenConcurrenciaTest(TransactionTestCase):
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
            restaurante=self.restaurante,
        )
        self.url = reverse("operativo:crear_orden")
        self.datos_orden = {"mesa": self.mesa.pk}

    def test_dos_solicitudes_simultaneas_solo_crean_una_orden(self):
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


class GestionMesasTest(TestBase):
    def setUp(self):
        super().setUp()
        for email, rol_nombre in (("admin.mesas@test.com", "ADMINISTRADOR"), ("mesero.mesas@test.com", "MESERO")):
            rol, _ = Rol.objects.get_or_create(nombre=rol_nombre)
            Usuario.objects.create_user(
                email=email, nombre=rol_nombre, password="testpass123", rol=rol, restaurante=self.restaurante,
            )
        self.url_lista = reverse("operativo:mesas_list")

    def test_admin_ve_botones_para_gestionar_mesas(self):
        self.client.login(email="admin.mesas@test.com", password="testpass123")
        respuesta = self.client.get(self.url_lista)
        self.assertContains(respuesta, reverse("operativo:mesa_crear"))
        self.assertContains(respuesta, reverse("operativo:mesa_editar", args=[self.mesa.pk]))
        self.assertContains(respuesta, reverse("operativo:mesa_eliminar", args=[self.mesa.pk]))

    def test_mesero_ve_mesas_pero_no_botones_de_gestion(self):
        self.client.login(email="mesero.mesas@test.com", password="testpass123")
        respuesta = self.client.get(self.url_lista)
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, reverse("operativo:mesa_crear"))
        self.assertNotContains(respuesta, reverse("operativo:mesa_editar", args=[self.mesa.pk]))
        self.assertEqual(self.client.get(reverse("operativo:mesa_crear")).status_code, 403)

    def test_admin_crea_mesa_en_su_sucursal(self):
        self.client.login(email="admin.mesas@test.com", password="testpass123")
        respuesta = self.client.post(reverse("operativo:mesa_crear"), {
            "numero": 5, "capacidad": 6, "sucursal": self.sucursal.pk, "activa": "on",
        })
        self.assertRedirects(respuesta, self.url_lista)
        mesa = Mesa.objects.get(numero=5)
        self.assertEqual(mesa.sucursal, self.sucursal)
        self.assertEqual(mesa.estado, Mesa.DISPONIBLE)

    def test_admin_elimina_mesa_sin_ordenes(self):
        self.client.login(email="admin.mesas@test.com", password="testpass123")
        respuesta = self.client.post(reverse("operativo:mesa_eliminar", args=[self.mesa.pk]))
        self.assertRedirects(respuesta, self.url_lista)
        self.assertFalse(Mesa.objects.filter(pk=self.mesa.pk).exists())

    def test_mesa_con_ordenes_no_se_elimina_y_avisa(self):
        Orden.objects.create(mesa=self.mesa, estado=Orden.ENTREGADA)
        self.client.login(email="admin.mesas@test.com", password="testpass123")
        respuesta = self.client.post(reverse("operativo:mesa_eliminar", args=[self.mesa.pk]), follow=True)
        self.assertRedirects(respuesta, reverse("operativo:mesa_editar", args=[self.mesa.pk]))
        self.assertContains(respuesta, "tiene órdenes registradas")
        self.assertTrue(Mesa.objects.filter(pk=self.mesa.pk).exists())
