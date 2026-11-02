from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from caja.models import Pago
from operativo.models import Mesa, Orden

from .base import CasoDeUsoTestCase


class PagosTests(CasoDeUsoTestCase):

    def setUp(self):
        self.orden = self.crear_orden(estado=Orden.LISTA)
        self.entrar_como("CAJERO")

    def cobrar(self, orden=None, metodo=None, monto="10000", referencia=""):
        orden = orden or self.orden
        return self.client.post(
            reverse("caja:cobrar_orden", args=[orden.pk]),
            {"metodo_pago": (metodo or self.efectivo).pk, "monto": monto, "referencia_transaccion": referencia},
        )

    def test_cu_pag_01_realizar_pago(self):
        respuesta = self.cobrar()
        factura = self.orden.factura
        self.assertRedirects(respuesta, reverse("caja:factura_detalle", args=[factura.pk]))
        self.assertEqual(Pago.objects.get().monto, Decimal("10000"))

    def test_cu_pag_02_pagar_en_efectivo(self):
        self.cobrar(monto="9999")
        self.assertEqual(Pago.objects.get().monto, Decimal("9999"))  # pago parcial permitido (cuenta mixta)
        self.cobrar(monto="20000")
        self.assertEqual(Pago.objects.get().metodo_pago, self.efectivo)

    def test_cu_pag_03_pagar_con_tarjeta_o_billetera(self):
        respuesta = self.cobrar(metodo=self.tarjeta, referencia="AUT-778899")
        pago = Pago.objects.get()
        self.assertEqual(pago.metodo_pago, self.tarjeta)
        self.assertEqual(pago.estado, Pago.PENDIENTE)  # en espera de la confirmación de la pasarela
        self.assertTrue(
            respuesta.url.startswith("https://checkout.wompi.co/p/") or respuesta.url.startswith("/caja/pasarela-simulada/"),
            msg=f"La redirección no esperada fue: {respuesta.url}",
        )

    def test_cu_pag_05_confirmar_pago(self):
        pendiente = self.crear_orden()
        self.cobrar(orden=pendiente)
        self.assertFalse(pendiente.pagos.exists())
        self.cobrar()
        self.cobrar()
        self.assertEqual(self.orden.pagos.count(), 1)

    def test_cu_pag_06_enviar_confirmacion_de_pago(self):
        self.cobrar()
        self.orden.refresh_from_db()
        self.mesa.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.ENTREGADA)
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)

    def test_cu_pag_10_registrar_venta(self):
        self.cobrar()
        ventas = self.client.get(reverse("caja:ventas_list")).context["ventas"]
        self.assertEqual(list(ventas), [self.orden])

    def test_cu_pag_12_enviar_datos_de_venta(self):
        self.cobrar()
        self.entrar_como("ADMINISTRADOR")
        self.assertEqual(self.client.get(reverse("reportes:dashboard")).context["ventas_hoy"], Decimal("10000"))
        por_metodo = list(self.client.get(reverse("reportes:reportes")).context["ventas_por_metodo"])
        self.assertEqual(por_metodo, [{"metodo_pago__nombre": "Efectivo", "total": Decimal("10000")}])

    def test_cu_pag_13_consultar_historial_de_ventas(self):
        self.cobrar()
        self.assertEqual(list(self.client.get(reverse("caja:pagos_list")).context["pagos"]), [Pago.objects.get()])
        self.entrar_como("MESERO")
        self.assertEqual(self.client.get(reverse("caja:pagos_list")).status_code, 403)

    def test_cu_pag_16_confirmar_pedido(self):
        sin_cuenta = self.crear_orden(estado=Orden.LISTA)
        Orden.objects.filter(pk=self.orden.pk).update(cuenta_solicitada_en=timezone.now())
        por_cobrar = list(self.client.get(reverse("caja:por_cobrar")).context["ordenes"])
        self.assertIn(self.orden, por_cobrar)
        self.assertNotIn(sin_cuenta, por_cobrar)
