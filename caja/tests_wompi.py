"""Flujo de cobro por QR con Wompi (sandbox): checkout, webhook, plan B por consulta y pantallas del celular."""
import hashlib
import json
from decimal import Decimal
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.test import override_settings
from django.urls import reverse

from . import conf, servicios
from .models import EventoPasarela, Factura, Pago
from .pasarelas import EventoPago, WompiPasarela, _checksum_wompi
from .tests_qr import BaseQRTest

LLAVES = {
    "PUBLIC_KEY": "pub_test_abc123",
    "INTEGRITY_SECRET": "test_integrity_xyz",
    "EVENTS_SECRET": "test_events_xyz",
    "CHECKOUT_URL": "https://checkout.wompi.co/p/",
}


def evento_wompi(pago, estado="APPROVED", monto_centavos=None, tx_id="tx-123"):
    """Construye un webhook como el que enviaría Wompi, con checksum válido."""
    evento = {
        "event": "transaction.updated",
        "data": {"transaction": {
            "id": tx_id, "status": estado, "reference": pago.referencia_pasarela,
            "amount_in_cents": monto_centavos if monto_centavos is not None else int(pago.total_cobrado * 100),
        }},
        "timestamp": 1760000000,
        "signature": {"properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"]},
    }
    evento["signature"]["checksum"] = _checksum_wompi(evento, evento["signature"]["properties"], LLAVES["EVENTS_SECRET"])
    return evento


@override_settings(PASARELA_PROVEEDOR="WOMPI", WOMPI=LLAVES)
class CobroQRConWompiTests(BaseQRTest):
    def _iniciar(self, monto="100000", propina=""):
        return self.client.post(self.url, {"monto": monto, "propina": propina, "confirmar": "1"})

    def _webhook(self, evento):
        return self.client.post(
            reverse("caja:webhook", args=["WOMPI"]), data=json.dumps(evento), content_type="application/json"
        )

    def test_pagar_redirige_al_checkout_de_wompi_y_deja_el_pago_pendiente(self):
        r = self._iniciar()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.url.startswith("https://checkout.wompi.co/p/"))
        pago = Pago.objects.get(orden=self.orden)
        self.assertEqual((pago.estado, pago.proveedor), (Pago.PENDIENTE, "WOMPI"))
        self.orden.refresh_from_db()
        self.assertNotEqual(self.orden.estado, "ENTREGADA")  # no se cierra hasta que Wompi confirme

    def test_el_checkout_lleva_monto_firma_y_retorno_al_celular(self):
        r = self._iniciar(propina="5000")
        q = {k: v[0] for k, v in parse_qs(urlparse(r.url).query).items()}
        pago = Pago.objects.get(orden=self.orden)
        self.assertEqual(q["amount-in-cents"], "10500000")
        self.assertEqual(q["reference"], pago.referencia_pasarela)
        firma = hashlib.sha256(f"{pago.referencia_pasarela}10500000COP{LLAVES['INTEGRITY_SECRET']}".encode()).hexdigest()
        self.assertEqual(q["signature:integrity"], firma)
        self.assertIn(reverse("caja:pago_listo", args=[self.enlace.token]), q["redirect-url"])

    @override_settings(CAJA_BASE_URL="https://demo.ngrok-free.app")
    def test_el_retorno_usa_la_direccion_publica_configurada(self):
        q = parse_qs(urlparse(self._iniciar().url).query)
        self.assertTrue(q["redirect-url"][0].startswith("https://demo.ngrok-free.app/caja/pagar/"))

    def test_no_se_puede_cobrar_mas_del_saldo_mientras_hay_un_cobro_en_curso(self):
        self._iniciar(monto="100000")
        r = self.client.post(self.url, {"monto": "1000", "confirmar": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Pago.objects.filter(orden=self.orden).count(), 1)

    def test_pantalla_del_celular_espera_mientras_esta_pendiente(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        r = self.client.get(reverse("caja:pago_listo", args=[self.enlace.token]), {"ref": pago.referencia_pasarela})
        self.assertContains(r, "Confirmando tu pago")
        self.assertContains(r, "Pago de prueba")  # llaves pub_test_

    def test_webhook_aprobado_cierra_la_cuenta_y_emite_comprobante(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        self.assertEqual(self._webhook(evento_wompi(pago)).status_code, 200)
        pago.refresh_from_db()
        self.orden.refresh_from_db()
        self.assertEqual(pago.estado, Pago.APROBADO)
        self.assertEqual(self.orden.estado, "ENTREGADA")
        self.assertTrue(Factura.objects.filter(orden=self.orden).exists())
        r = self.client.get(reverse("caja:pago_listo", args=[self.enlace.token]), {"ref": pago.referencia_pasarela})
        self.assertContains(r, "Pago recibido")

    def test_webhook_con_firma_falsa_se_rechaza(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        evento = evento_wompi(pago)
        evento["signature"]["checksum"] = "0" * 64
        self.assertEqual(self._webhook(evento).status_code, 400)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.PENDIENTE)

    def test_webhook_con_monto_distinto_no_aprueba(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        self._webhook(evento_wompi(pago, monto_centavos=100))
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.PENDIENTE)
        self.assertTrue(EventoPasarela.objects.filter(resultado__contains="monto").exists())

    def test_el_mismo_webhook_dos_veces_se_procesa_una_sola_vez(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        evento = evento_wompi(pago)
        self._webhook(evento)
        self._webhook(evento)
        self.assertEqual(EventoPasarela.objects.filter(evento_id="tx-123:APPROVED").count(), 1)
        self.assertEqual(Factura.objects.filter(orden=self.orden).count(), 1)

    def test_pago_rechazado_muestra_reintento_y_libera_el_saldo(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        self._webhook(evento_wompi(pago, estado="DECLINED"))
        r = self.client.get(reverse("caja:pago_listo", args=[self.enlace.token]), {"ref": pago.referencia_pasarela})
        self.assertContains(r, "no se completó")
        self.assertEqual(servicios.saldo_disponible(self.orden), Decimal("100000"))

    def test_plan_b_si_el_webhook_no_llega_se_confirma_con_el_id_de_la_transaccion(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        aprobado = EventoPago(
            evento_id="tx-9:APPROVED", id_transaccion="tx-9", referencia=pago.referencia_pasarela,
            estado="APROBADO", monto_centavos=int(pago.total_cobrado * 100),
        )
        with mock.patch.object(WompiPasarela, "consultar_transaccion", return_value=aprobado):
            r = self.client.get(
                reverse("caja:pago_listo", args=[self.enlace.token]), {"ref": pago.referencia_pasarela, "id": "tx-9"}
            )
        self.assertContains(r, "Pago recibido")
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.APROBADO)

    def test_plan_b_ignora_una_transaccion_de_otra_referencia(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        ajeno = EventoPago(
            evento_id="tx-8:APPROVED", id_transaccion="tx-8", referencia="SB-999-otra",
            estado="APROBADO", monto_centavos=int(pago.total_cobrado * 100),
        )
        with mock.patch.object(WompiPasarela, "consultar_transaccion", return_value=ajeno):
            self.client.get(reverse("caja:pago_listo", args=[self.enlace.token]), {"ref": pago.referencia_pasarela, "id": "tx-8"})
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.PENDIENTE)

    def test_estado_json_para_la_pantalla_de_espera(self):
        self._iniciar()
        pago = Pago.objects.get(orden=self.orden)
        url = reverse("caja:estado_pago", args=[self.enlace.token])
        self.assertEqual(self.client.get(url, {"ref": pago.referencia_pasarela}).json(), {"estado": "PENDIENTE"})
        self._webhook(evento_wompi(pago))
        self.assertEqual(self.client.get(url, {"ref": pago.referencia_pasarela}).json(), {"estado": "APROBADO"})

    def test_estado_de_un_pago_ajeno_da_404(self):
        self.assertEqual(self.client.get(reverse("caja:estado_pago", args=[self.enlace.token]), {"ref": "SB-1-x"}).status_code, 404)


@override_settings(PASARELA_PROVEEDOR="WOMPI", WOMPI=LLAVES)
class ConsultaApiWompiTests(BaseQRTest):
    def _respuesta(self, datos):
        cm = mock.MagicMock()
        cm.__enter__.return_value.read.return_value = json.dumps({"data": datos}).encode()
        return cm

    def test_lee_la_transaccion_del_sandbox(self):
        datos = {"id": "tx-1", "status": "APPROVED", "reference": "SB-1-a", "amount_in_cents": 5000000}
        with mock.patch("caja.pasarelas.urllib.request.urlopen", return_value=self._respuesta(datos)) as m:
            ev = WompiPasarela().consultar_transaccion("tx-1")
        self.assertEqual(m.call_args[0][0], "https://sandbox.wompi.co/v1/transactions/tx-1")
        self.assertEqual((ev.estado, ev.referencia, ev.monto_centavos), ("APROBADO", "SB-1-a", 5000000))

    def test_si_la_consulta_falla_devuelve_none(self):
        with mock.patch("caja.pasarelas.urllib.request.urlopen", side_effect=OSError("sin red")):
            self.assertIsNone(WompiPasarela().consultar_transaccion("tx-1"))

    def test_modo_prueba_depende_de_las_llaves(self):
        self.assertTrue(conf.modo_prueba())
        with override_settings(WOMPI={**LLAVES, "PUBLIC_KEY": "pub_prod_real"}):
            self.assertFalse(conf.modo_prueba())
            self.assertEqual(conf.wompi_api_url(), "https://production.wompi.co/v1")