import json
from decimal import Decimal

from django.test import TestCase, override_settings

from django.urls import reverse

from catalogo.models import Categoria, Producto
from cuentas.models import Rol, Usuario
from operativo.models import DetalleOrden, Mesa, Orden
from restaurantes.models import Restaurante, Sucursal

from . import servicios
from .models import AuditoriaCobro, EventoPasarela, MetodoPago, Pago
from .pasarelas import FirmaInvalida, WompiPasarela, _checksum_wompi
from .servicios import CobroInvalido


WOMPI_CFG = {"PUBLIC_KEY": "pub_test_x", "INTEGRITY_SECRET": "integ", "EVENTS_SECRET": "ev_secret",
             "CHECKOUT_URL": "https://checkout.wompi.co/p/"}


@override_settings(PASARELA_PROVEEDOR="SIMULADA")
class BaseCajaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        rest = Restaurante.objects.create(nombre="R", nif="1", email="r@r.co", direccion="x")
        suc = Sucursal.objects.create(restaurante=rest, nombre="Centro")
        cls.mesa = Mesa.objects.create(numero=1, sucursal=suc, estado=Mesa.OCUPADA)
        cat = Categoria.objects.create(nombre="Platos")
        cls.prod = Producto.objects.create(nombre="Bandeja", precio=Decimal("50000"), categoria=cat, sucursal=suc)
        cls.efectivo = MetodoPago.objects.create(nombre="Efectivo")
        cls.tarjeta = MetodoPago.objects.create(nombre="Tarjeta", usa_pasarela=True)
        cls.cajero = Usuario.objects.create_user("caja@x.co", "Cajero Uno", "pass12345", rol=Rol.objects.create(nombre="CAJERO"))
        cls.mesero = Usuario.objects.create_user("mesero@x.co", "Mesero", "pass12345", rol=Rol.objects.create(nombre="MESERO"))

    def setUp(self):
        self.orden = Orden.objects.create(mesa=self.mesa, estado=Orden.LISTA)
        DetalleOrden.objects.create(orden=self.orden, producto=self.prod, cantidad=2, precio_unitario=Decimal("50000"))
        # total = 100.000


class PagoMixtoTests(BaseCajaTest):
    def test_pago_parcial_no_cierra_la_orden(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("40000"), usuario=self.cajero)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.LISTA)
        self.assertEqual(servicios.saldo_pendiente(self.orden), Decimal("60000"))

    def test_dos_pagos_completan_y_liberan_la_mesa(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("40000"), usuario=self.cajero)
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("60000"), usuario=self.cajero)
        self.orden.refresh_from_db(); self.mesa.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.ENTREGADA)
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)

    def test_propina_no_abona_a_la_cuenta(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("90000"), propina=Decimal("20000"), usuario=self.cajero)
        self.assertEqual(servicios.saldo_pendiente(self.orden), Decimal("10000"))

    def test_no_se_puede_cobrar_mas_que_el_saldo(self):
        with self.assertRaises(CobroInvalido):
            servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("100001"), usuario=self.cajero)
        self.assertEqual(Pago.objects.count(), 0)

    def test_el_cobro_queda_auditado(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("30000"), usuario=self.cajero, ip="10.0.0.5")
        a = AuditoriaCobro.objects.get()
        self.assertEqual((a.accion, a.usuario, a.monto, a.ip), (AuditoriaCobro.COBRO, self.cajero, Decimal("30000"), "10.0.0.5"))


class PasarelaSimuladaTests(BaseCajaTest):
    def _iniciar(self, monto="100000"):
        return servicios.iniciar_cobro_tarjeta(self.orden.pk, metodo=self.tarjeta, monto=Decimal(monto), usuario=self.cajero)

    def test_pendiente_no_cierra_hasta_el_webhook(self):
        pago, _ = self._iniciar()
        self.orden.refresh_from_db()
        self.assertEqual((pago.estado, self.orden.estado), (Pago.PENDIENTE, Orden.LISTA))

    def test_webhook_aprobado_cierra_la_orden(self):
        pago, pas = self._iniciar()
        r = servicios.procesar_evento(pas, pas.construir_evento(pago, "APPROVED"), {})
        pago.refresh_from_db(); self.orden.refresh_from_db()
        self.assertEqual((r, pago.estado, self.orden.estado), ("aprobado", Pago.APROBADO, Orden.ENTREGADA))

    def test_mismo_evento_dos_veces_no_duplica(self):
        pago, pas = self._iniciar("40000")
        cuerpo = pas.construir_evento(pago, "APPROVED")
        self.assertEqual(servicios.procesar_evento(pas, cuerpo, {}), "aprobado")
        self.assertEqual(servicios.procesar_evento(pas, cuerpo, {}), "duplicado")
        self.assertEqual(EventoPasarela.objects.count(), 1)
        self.assertEqual(AuditoriaCobro.objects.filter(accion=AuditoriaCobro.PASARELA_APROBADA).count(), 1)
        self.assertEqual(servicios.saldo_pendiente(self.orden), Decimal("60000"))

    def test_rechazado_deja_la_orden_abierta(self):
        pago, pas = self._iniciar()
        servicios.procesar_evento(pas, pas.construir_evento(pago, "DECLINED"), {})
        pago.refresh_from_db(); self.orden.refresh_from_db()
        self.assertEqual((pago.estado, self.orden.estado), (Pago.RECHAZADO, Orden.LISTA))

    def test_evento_con_monto_distinto_genera_alerta(self):
        pago, pas = self._iniciar()
        evento = json.loads(pas.construir_evento(pago, "APPROVED"))
        evento["data"]["transaction"]["amount_in_cents"] = 100
        evento["signature"]["checksum"] = _checksum_wompi(evento, evento["signature"]["properties"], "secreto-local-solo-para-demo")
        r = servicios.procesar_evento(pas, json.dumps(evento).encode(), {})
        pago.refresh_from_db()
        self.assertEqual((r, pago.estado), ("alerta: monto no coincide", Pago.PENDIENTE))
        self.assertTrue(AuditoriaCobro.objects.filter(accion=AuditoriaCobro.ALERTA).exists())

    def test_firma_invalida_se_rechaza(self):
        pago, pas = self._iniciar()
        evento = json.loads(pas.construir_evento(pago, "APPROVED"))
        evento["signature"]["checksum"] = "0" * 64
        with self.assertRaises(FirmaInvalida):
            servicios.procesar_evento(pas, json.dumps(evento).encode(), {})
        self.assertEqual(EventoPasarela.objects.count(), 0)

    def test_no_se_reserva_mas_saldo_del_que_hay(self):
        self._iniciar("70000")
        with self.assertRaises(CobroInvalido):
            self._iniciar("40000")


@override_settings(WOMPI=WOMPI_CFG, PASARELA_PROVEEDOR="WOMPI")
class WompiTests(BaseCajaTest):
    def _evento(self, pago, estado="APPROVED", secreto="ev_secret"):
        evento = {"event": "transaction.updated", "environment": "test", "timestamp": 1530291411,
                  "data": {"transaction": {"id": "1234-1610641025-49201", "status": estado,
                                           "reference": pago.referencia_pasarela,
                                           "amount_in_cents": int(pago.total_cobrado * 100)}},
                  "signature": {"properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"]}}
        evento["signature"]["checksum"] = _checksum_wompi(evento, evento["signature"]["properties"], secreto).upper()
        return evento

    def test_url_checkout_trae_firma_y_monto_en_centavos(self):
        pago, pas = servicios.iniciar_cobro_tarjeta(self.orden.pk, metodo=self.tarjeta, monto=Decimal("100000"), propina=Decimal("5000"))
        self.assertIsInstance(pas, WompiPasarela)
        self.client.force_login(self.cajero)
        url = pas.url_checkout(self.client.get("/").wsgi_request, pago)
        self.assertIn("amount-in-cents=10500000", url)
        self.assertIn(f"reference={pago.referencia_pasarela}", url)
        self.assertIn("signature%3Aintegrity=", url)

    def test_webhook_http_aprueba_y_es_idempotente(self):
        pago, _ = servicios.iniciar_cobro_tarjeta(self.orden.pk, metodo=self.tarjeta, monto=Decimal("100000"))
        cuerpo = json.dumps(self._evento(pago))
        url = reverse("caja:webhook", args=["wompi"])
        for _ in range(2):
            self.assertEqual(self.client.post(url, cuerpo, content_type="application/json").status_code, 200)
        pago.refresh_from_db()
        self.assertEqual((pago.estado, pago.id_transaccion_pasarela), (Pago.APROBADO, "1234-1610641025-49201"))
        self.assertEqual(AuditoriaCobro.objects.filter(accion=AuditoriaCobro.PASARELA_APROBADA).count(), 1)

    def test_webhook_con_firma_falsa_da_400(self):
        pago, _ = servicios.iniciar_cobro_tarjeta(self.orden.pk, metodo=self.tarjeta, monto=Decimal("100000"))
        cuerpo = json.dumps(self._evento(pago, secreto="otro_secreto"))
        r = self.client.post(reverse("caja:webhook", args=["wompi"]), cuerpo, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        pago.refresh_from_db()
        self.assertEqual(pago.estado, Pago.PENDIENTE)

    def test_webhook_solo_acepta_post(self):
        self.assertEqual(self.client.get(reverse("caja:webhook", args=["wompi"])).status_code, 405)


class VistasCajaTests(BaseCajaTest):
    def test_anonimo_es_redirigido_al_login(self):
        r = self.client.get(reverse("caja:cobrar_orden", args=[self.orden.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url)

    def test_mesero_no_puede_cobrar(self):
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(reverse("caja:cobrar_orden", args=[self.orden.pk])).status_code, 403)

    def test_cajero_cobra_en_efectivo_con_propina(self):
        self.client.force_login(self.cajero)
        r = self.client.post(reverse("caja:cobrar_orden", args=[self.orden.pk]), {
            "metodo_pago": self.efectivo.pk, "monto": "100000", "propina": "8000", "efectivo_recibido": "120000"})
        self.assertRedirects(r, reverse("caja:factura_detalle", args=[Orden.objects.get(pk=self.orden.pk).factura.pk]), fetch_redirect_response=False)
        pago = Pago.objects.get()
        self.assertEqual((pago.propina, pago.cobrado_por), (Decimal("8000"), self.cajero))

    def test_cobro_con_tarjeta_redirige_a_la_pasarela(self):
        self.client.force_login(self.cajero)
        r = self.client.post(reverse("caja:cobrar_orden", args=[self.orden.pk]), {"metodo_pago": self.tarjeta.pk, "monto": "100000"})
        pago = Pago.objects.get()
        self.assertEqual(pago.estado, Pago.PENDIENTE)
        self.assertRedirects(r, reverse("caja:pasarela_simulada", args=[pago.referencia_pasarela]), fetch_redirect_response=False)

    def test_flujo_simulado_completo_por_http(self):
        self.client.force_login(self.cajero)
        self.client.post(reverse("caja:cobrar_orden", args=[self.orden.pk]), {"metodo_pago": self.tarjeta.pk, "monto": "100000"})
        pago = Pago.objects.get()
        self.client.post(reverse("caja:pasarela_simulada", args=[pago.referencia_pasarela]), {"resultado": "aprobar"})
        pago.refresh_from_db(); self.orden.refresh_from_db()
        self.assertEqual((pago.estado, self.orden.estado), (Pago.APROBADO, Orden.ENTREGADA))

    def test_auditoria_solo_para_administrador(self):
        self.client.force_login(self.cajero)
        self.assertEqual(self.client.get(reverse("caja:auditoria_list")).status_code, 403)
        admin = Usuario.objects.create_superuser("a@x.co", "Admin", "pass12345")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse("caja:auditoria_list")).status_code, 200)
