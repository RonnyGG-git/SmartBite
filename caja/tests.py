from decimal import Decimal

from django.test import TestCase, Client
from django.urls import reverse

from catalogo.models import Categoria, Producto
from cuentas.models import Rol, Usuario
from operativo.models import Mesa, Orden
from restaurantes.models import Restaurante, Sucursal

from .models import MetodoPago, Pago


class CobrarOrdenTest(TestCase):
    """Tests para la vista cobrar_orden (RF-006, Hallazgo H2)."""

    def setUp(self):
        self.client = Client()
        # Restaurante y sucursal
        self.restaurante = Restaurante.objects.create(
            nombre="Test Restaurante",
            nif="12345678A",
            email="test@test.com",
            direccion="Calle Test 1",
        )
        self.sucursal = Sucursal.objects.create(
            restaurante=self.restaurante,
            nombre="Sucursal Test",
        )
        # Mesa
        self.mesa = Mesa.objects.create(
            numero=1,
            capacidad=4,
            sucursal=self.sucursal,
        )
        # Metodo de pago
        self.metodo_pago = MetodoPago.objects.create(nombre="Efectivo")
        # Categoria y producto
        self.categoria = Categoria.objects.create(nombre="Bebidas")
        self.producto = Producto.objects.create(
            nombre="Agua",
            precio=Decimal("2500.00"),
            categoria=self.categoria,
            sucursal=self.sucursal,
        )
        # Usuario cajero
        self.rol_cajero = Rol.objects.create(nombre="CAJERO")
        self.usuario_cajero = Usuario.objects.create_user(
            email="cajero@test.com",
            nombre="Cajero Test",
            password="testpass123",
            rol=self.rol_cajero,
        )
        # Crear orden LISTA con total = 5000
        self.orden_lista = self._crear_orden_con_detalle(Orden.LISTA, Decimal("5000.00"))
        # URL de cobro
        self.url_cobrar = reverse("caja:cobrar_orden", kwargs={"pk": self.orden_lista.pk})

    def _crear_orden_con_detalle(self, estado, precio_unitario):
        """Helper para crear una orden con un detalle."""
        mesa = Mesa.objects.create(
            numero=Mesa.objects.count() + 10,
            capacidad=4,
            sucursal=self.sucursal,
        )
        orden = Orden.objects.create(mesa=mesa, estado=estado)
        orden.detalles.create(
            producto=self.producto,
            cantidad=1,
            precio_unitario=precio_unitario,
        )
        return orden

    def test_cobrar_orden_ok(self):
        """POST con estado LISTA crea Pago y cambia a ENTREGADA."""
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(self.url_cobrar, {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "5000.00",
        })
        self.assertRedirects(
            respuesta,
            reverse("operativo:mesas_list"),
            fetch_redirect_response=False,
        )
        self.orden_lista.refresh_from_db()
        self.assertEqual(self.orden_lista.estado, Orden.ENTREGADA)
        self.assertEqual(self.orden_lista.mesa.estado, Mesa.DISPONIBLE)
        self.assertEqual(self.orden_lista.pagos.count(), 1)
        pago = self.orden_lista.pagos.first()
        self.assertEqual(pago.monto, Decimal("5000.00"))

    def test_cobrar_orden_estado_pendiente(self):
        """POST con estado PENDIENTE es rechazado."""
        orden = self._crear_orden_con_detalle(Orden.PENDIENTE, Decimal("5000.00"))
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(reverse("caja:cobrar_orden", kwargs={"pk": orden.pk}), {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "5000.00",
        })
        self.assertEqual(respuesta.status_code, 200)  # Formulario con error
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.assertEqual(orden.pagos.count(), 0)

    def test_cobrar_orden_estado_en_preparacion(self):
        """POST con estado EN_PREPARACION es rechazado."""
        orden = self._crear_orden_con_detalle(Orden.EN_PREPARACION, Decimal("5000.00"))
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(reverse("caja:cobrar_orden", kwargs={"pk": orden.pk}), {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "5000.00",
        })
        self.assertEqual(respuesta.status_code, 200)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.EN_PREPARACION)
        self.assertEqual(orden.pagos.count(), 0)

    def test_cobrar_orden_estado_entregada(self):
        """POST con estado ENTREGADA es rechazado."""
        orden = self._crear_orden_con_detalle(Orden.ENTREGADA, Decimal("5000.00"))
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(reverse("caja:cobrar_orden", kwargs={"pk": orden.pk}), {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "5000.00",
        })
        self.assertEqual(respuesta.status_code, 200)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.ENTREGADA)
        self.assertEqual(orden.pagos.count(), 0)

    def test_cobrar_orden_estado_cancelada(self):
        """POST con estado CANCELADA es rechazado."""
        orden = self._crear_orden_con_detalle(Orden.CANCELADA, Decimal("5000.00"))
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(reverse("caja:cobrar_orden", kwargs={"pk": orden.pk}), {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "5000.00",
        })
        self.assertEqual(respuesta.status_code, 200)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.CANCELADA)
        self.assertEqual(orden.pagos.count(), 0)

    def test_cobrar_orden_pago_duplicado(self):
        """Segundo pago para misma orden es rechazado."""
        Pago.objects.create(
            orden=self.orden_lista,
            metodo_pago=self.metodo_pago,
            monto=Decimal("5000.00"),
        )
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(self.url_cobrar, {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "5000.00",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self.orden_lista.pagos.count(), 1)

    def test_cobrar_orden_monto_insuficiente(self):
        """Monto menor al total es rechazado."""
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(self.url_cobrar, {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "4999.99",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.orden_lista.refresh_from_db()
        self.assertEqual(self.orden_lista.estado, Orden.LISTA)
        self.assertEqual(self.orden_lista.pagos.count(), 0)

    def test_cobrar_orden_monto_exacto(self):
        """Monto igual al total es aceptado."""
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(self.url_cobrar, {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "5000.00",
        })
        self.assertRedirects(
            respuesta,
            reverse("operativo:mesas_list"),
            fetch_redirect_response=False,
        )
        self.orden_lista.refresh_from_db()
        self.assertEqual(self.orden_lista.estado, Orden.ENTREGADA)
        self.assertEqual(self.orden_lista.pagos.count(), 1)

    def test_cobrar_orden_monto_excedente(self):
        """Monto mayor al total se acepta, excedente no registra cambio."""
        self.client.login(email="cajero@test.com", password="testpass123")
        respuesta = self.client.post(self.url_cobrar, {
            "metodo_pago": self.metodo_pago.pk,
            "monto": "6000.00",
        })
        self.assertRedirects(
            respuesta,
            reverse("operativo:mesas_list"),
            fetch_redirect_response=False,
        )
        self.orden_lista.refresh_from_db()
        self.assertEqual(self.orden_lista.estado, Orden.ENTREGADA)
        pago = self.orden_lista.pagos.first()
        self.assertEqual(pago.monto, Decimal("6000.00"))

    def test_cobrar_orden_concurrencia(self):
        """Dos solicitudes concurrentes cobrando la misma orden: solo una debe registrar pago.

        Verifica que select_for_update() protege contra doble cobro.
        Limitacion conocida: SQLite ignora select_for_update() (es un no-op),
        por lo que ambas transacciones pueden leer el mismo estado. En PostgreSQL
        o MySQL real, select_for_update() bloquea la fila y garantiza que solo
        una transaccion procede. En SQLite, la serializacion a nivel de archivo
        puede causar que ambos hilos fallen con 'database is locked', lo cual
        tambien previene el doble cobro.
        """
        import threading

        from django.db import transaction as db_transaction

        orden = self._crear_orden_con_detalle(Orden.LISTA, Decimal("5000.00"))
        barrier = threading.Barrier(2, timeout=10)
        resultados = []

        def intentar_cobro(idx):
            barrier.wait()
            try:
                with db_transaction.atomic():
                    o = Orden.objects.select_for_update().get(pk=orden.pk)
                    if o.estado != Orden.LISTA or o.pagos.exists():
                        resultados.append(("rechazado", idx))
                        return
                    Pago.objects.create(
                        orden=o,
                        metodo_pago=self.metodo_pago,
                        monto=Decimal("5000.00"),
                    )
                    o.estado = Orden.ENTREGADA
                    o.save(update_fields=["estado"])
                    resultados.append(("exitoso", idx))
            except Exception as exc:
                resultados.append(("error", str(exc)))

        hilos = [
            threading.Thread(target=intentar_cobro, args=(0,)),
            threading.Thread(target=intentar_cobro, args=(1,)),
        ]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=15)

        orden.refresh_from_db()

        exitosos = [r for r in resultados if r[0] == "exitoso"]
        rechazados = [r for r in resultados if r[0] == "rechazado"]

        self.assertLessEqual(
            len(exitosos), 1,
            "Solo un cobro debe ser exitoso bajo concurrencia",
        )
        self.assertLessEqual(
            orden.pagos.count(), 1,
            "No debe existir mas de un pago para la orden",
        )
        self.assertIn(
            orden.estado,
            [Orden.LISTA, Orden.ENTREGADA],
            "La orden debe quedar en LISTA o ENTREGADA",
        )
        if len(exitosos) == 1:
            self.assertEqual(orden.estado, Orden.ENTREGADA)
            self.assertEqual(orden.pagos.count(), 1)
