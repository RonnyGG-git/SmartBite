from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.test import TestCase, override_settings


from catalogo.models import Categoria, Producto
from cuentas.models import Rol, Usuario
from operativo.models import Cliente, DetalleOrden, Mesa, Orden
from restaurantes.models import Restaurante, Sucursal

from . import servicios
from .facturacion import desglose_inc
from .models import AuditoriaCobro, EnlacePago, Factura, MetodoPago, Pago
from .qr import obtener_enlace_pago
from .vistas_qr import leer_monto

@override_settings(PASARELA_PROVEEDOR="SIMULADA")
class BaseQRTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        rest = Restaurante.objects.create(nombre="La Cocina", nif="900123456", email="r@r.co", direccion="Calle 1")
        suc = Sucursal.objects.create(restaurante=rest, nombre="Centro")
        cls.mesa = Mesa.objects.create(numero=7, sucursal=suc, estado=Mesa.OCUPADA)
        cat = Categoria.objects.create(nombre="Platos")
        cls.prod = Producto.objects.create(nombre="Bandeja", precio=Decimal("50000"), categoria=cat, sucursal=suc)
        cls.efectivo = MetodoPago.objects.create(nombre="Efectivo")
        cls.cajero = Usuario.objects.create_user("caja@x.co", "Cajero", "pass12345", rol=Rol.objects.create(nombre="CAJERO"))
        cls.mesero = Usuario.objects.create_user("mesero@x.co", "Mesero", "pass12345", rol=Rol.objects.create(nombre="MESERO"))

    def setUp(self):
        self.orden = Orden.objects.create(mesa=self.mesa, estado=Orden.LISTA)
        DetalleOrden.objects.create(orden=self.orden, producto=self.prod, cantidad=2, precio_unitario=Decimal("50000"))
        self.enlace = obtener_enlace_pago(self.orden, self.cajero)  # total = 100.000
        self.url = reverse("caja:pagar_cliente", args=[self.enlace.token])


class LecturaMontoTests(TestCase):
    def test_formatos_colombianos(self):
        self.assertEqual(leer_monto("50000"), Decimal("50000"))
        self.assertEqual(leer_monto("50.000"), Decimal("50000"))
        self.assertEqual(leer_monto("$ 1.250.000"), Decimal("1250000"))
        self.assertEqual(leer_monto("50.000,50"), Decimal("50000.50"))
        self.assertEqual(leer_monto("50,5"), Decimal("50.5"))
        self.assertIsNone(leer_monto("abc"))
        self.assertIsNone(leer_monto(""))


class PagoDesdeCelularTests(BaseQRTest):
    def test_el_cliente_ve_la_cuenta_sin_iniciar_sesion(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "$100.000")
        self.assertContains(r, "La Cocina")

    def test_token_desconocido_da_404(self):
        self.assertEqual(self.client.get(reverse("caja:pagar_cliente", args=["no-existe"])).status_code, 404)

    def test_qr_vencido_no_deja_pagar(self):
        EnlacePago.objects.filter(pk=self.enlace.pk).update(expira_en=timezone.now() - timezone.timedelta(minutes=1))
        r = self.client.post(self.url, {"monto": "100000"})
        self.assertContains(r, "venció")
        self.assertEqual(Pago.objects.count(), 0)

    def test_monto_menor_muestra_aviso_y_no_cobra(self):
        r = self.client.post(self.url, {"monto": "40000"})
        self.assertContains(r, "menor al saldo")
        self.assertContains(r, "$60.000")
        self.assertEqual(Pago.objects.count(), 0)

    def test_monto_mayor_se_rechaza(self):
        r = self.client.post(self.url, {"monto": "150000"})
        self.assertContains(r, "supera")
        self.assertEqual(Pago.objects.count(), 0)

    def test_confirmando_el_aviso_se_paga_solo_esa_parte(self):
        r = self.client.post(self.url, {"monto": "40.000", "confirmar_parcial": "1"})
        self.assertEqual(r.status_code, 302)
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.LISTA)
        self.assertEqual(servicios.saldo_pendiente(self.orden), Decimal("60000"))
        self.assertEqual(Pago.objects.get().estado, Pago.APROBADO)

    def test_monto_exacto_paga_de_una_vez_y_emite_comprobante(self):
        r = self.client.post(self.url, {"monto": "100000", "propina": "10000"})
        pago = Pago.objects.get()
        self.assertRedirects(r, f"{reverse('caja:pago_listo', args=[self.enlace.token])}?ref={pago.referencia_pasarela}",
                             fetch_redirect_response=False)
        self.orden.refresh_from_db(); self.mesa.refresh_from_db()
        self.assertEqual((pago.estado, pago.propina, pago.cobrado_por), (Pago.APROBADO, Decimal("10000"), None))
        self.assertEqual((self.orden.estado, self.mesa.estado), (Orden.ENTREGADA, Mesa.DISPONIBLE))
        self.assertEqual(Factura.objects.filter(orden=self.orden).count(), 1)

    def test_pantalla_de_exito_y_comprobante_publico(self):
        self.client.post(self.url, {"monto": "100000"})
        pago = Pago.objects.get()
        listo = self.client.get(f"{reverse('caja:pago_listo', args=[self.enlace.token])}?ref={pago.referencia_pasarela}")
        self.assertContains(listo, "Pago recibido")
        self.assertContains(listo, "Ver mi comprobante")
        comprobante = self.client.get(reverse("caja:factura_publica", args=[self.enlace.token]))
        self.assertContains(comprobante, "SB-000001")
        self.assertContains(comprobante, "SIMULADO")

    def test_cuenta_ya_pagada_no_permite_pagar_otra_vez(self):
        self.client.post(self.url, {"monto": "100000"})
        r = self.client.post(self.url, {"monto": "1000"})
        self.assertContains(r, "ya está pagada")
        self.assertEqual(Pago.objects.count(), 1)

    def test_el_pago_por_qr_queda_auditado_como_qr(self):
        self.client.post(self.url, {"monto": "100000"})
        self.assertTrue(AuditoriaCobro.objects.filter(accion=AuditoriaCobro.PASARELA_INICIADA, detalle__contains="QR").exists())
        self.assertTrue(AuditoriaCobro.objects.filter(accion=AuditoriaCobro.PASARELA_APROBADA).exists())

    def test_metodo_qr_no_aparece_en_la_lista_del_cajero(self):
        self.client.post(self.url, {"monto": "100000"})
        self.assertFalse(MetodoPago.objects.get(nombre="Pago QR").activo)


class PantallaQRCajeroTests(BaseQRTest):
    def test_solo_caja_ve_el_qr(self):
        ruta = reverse("caja:qr_cobro", args=[self.orden.pk])
        self.assertEqual(self.client.get(ruta).status_code, 302)
        self.client.force_login(self.mesero)
        self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_muestra_el_qr_con_el_enlace_del_cliente(self):
        self.client.force_login(self.cajero)
        r = self.client.get(reverse("caja:qr_cobro", args=[self.orden.pk]))
        self.assertContains(r, "data:image/png;base64,")
        self.assertContains(r, reverse("caja:pagar_cliente", args=[self.enlace.token]))

    def test_usa_la_direccion_configurada_para_el_celular(self):
        self.client.force_login(self.cajero)
        with self.settings(CAJA_BASE_URL="http://192.168.1.15:8000"):
            r = self.client.get(reverse("caja:qr_cobro", args=[self.orden.pk]))
        self.assertContains(r, "http://192.168.1.15:8000/caja/pagar/")

    def test_estado_json_refleja_el_pago_del_celular(self):
        self.client.force_login(self.cajero)
        url = reverse("caja:estado_orden", args=[self.orden.pk])
        self.assertEqual(self.client.get(url).json()["saldo"], 100000.0)
        self.client.post(self.url, {"monto": "40000", "confirmar_parcial": "1"})
        d = self.client.get(url).json()
        self.assertEqual((d["saldo"], d["pagos"], d["pagada"]), (60000.0, 1, False))
        self.client.post(self.url, {"monto": "60000"})
        d = self.client.get(url).json()
        self.assertTrue(d["pagada"])
        self.assertTrue(d["factura_url"])


class ComprobanteTests(BaseQRTest):
    def test_desglose_del_impuesto_al_consumo(self):
        base, inc = desglose_inc(Decimal("100000"))
        self.assertEqual((base, inc), (Decimal("92592.59"), Decimal("7407.41")))
        self.assertEqual(base + inc, Decimal("100000"))

    def test_la_propina_va_aparte_y_no_entra_en_la_base(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("100000"),
                                        propina=Decimal("15000"), usuario=self.cajero)
        f = self.orden.factura
        self.assertEqual((f.total_consumo, f.propina, f.total_pagado), (Decimal("100000"), Decimal("15000"), Decimal("115000")))
        self.assertEqual(f.base_gravable, Decimal("92592.59"))

    def test_sin_cliente_es_consumidor_final(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("100000"), usuario=self.cajero)
        f = self.orden.factura
        self.assertEqual((f.cliente_nombre, f.cliente_documento), ("Consumidor final", "222222222222"))

    def test_con_cliente_usa_sus_datos(self):
        self.orden.cliente = Cliente.objects.create(nombre="Ana Pérez", numero_documento="1043000111", email="ana@x.co")
        self.orden.save()
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("100000"), usuario=self.cajero)
        f = self.orden.factura
        self.assertEqual((f.cliente_nombre, f.cliente_documento, f.cliente_email), ("Ana Pérez", "1043000111", "ana@x.co"))

    def test_pago_mixto_queda_en_un_solo_comprobante(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("30000"), usuario=self.cajero)
        self.assertFalse(Factura.objects.exists())          # aún no está pagada
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("70000"), usuario=self.cajero)
        self.assertEqual(Factura.objects.count(), 1)
        self.assertEqual(len(Factura.objects.get().detalle["pagos"]), 2)

    def test_numeracion_consecutiva(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("100000"), usuario=self.cajero)
        otra = Orden.objects.create(mesa=self.mesa, estado=Orden.LISTA)
        DetalleOrden.objects.create(orden=otra, producto=self.prod, cantidad=1, precio_unitario=Decimal("50000"))
        servicios.registrar_pago_manual(otra.pk, metodo=self.efectivo, monto=Decimal("50000"), usuario=self.cajero)
        self.assertEqual(list(Factura.objects.order_by("numero").values_list("numero", flat=True)), [1, 2])

    def test_listado_y_detalle_para_caja(self):
        servicios.registrar_pago_manual(self.orden.pk, metodo=self.efectivo, monto=Decimal("100000"), usuario=self.cajero)
        self.client.force_login(self.cajero)
        self.assertContains(self.client.get(reverse("caja:facturas_list")), "SB-000001")
        r = self.client.get(reverse("caja:factura_detalle", args=[self.orden.factura.pk]))
        self.assertContains(r, "Imp. nacional al consumo 8%")
        self.assertContains(r, "Imprimir")