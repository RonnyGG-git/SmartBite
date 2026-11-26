from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from caja.models import MetodoPago, Pago
from core.testing import crear_escenario, crear_usuario
from operativo.models import DetalleOrden, Orden
from restaurantes.models import Restaurante, Sucursal


def api_de(usuario):
    cliente = APIClient()
    token, _ = Token.objects.get_or_create(user=usuario)
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return cliente


def texto_del_pdf(contenido):
    import base64
    import re
    import zlib

    partes = []
    for flujo in re.findall(rb"stream\s(.*?)~>", contenido, re.S):
        try:
            partes.append(zlib.decompress(base64.a85decode(flujo.strip())).decode("latin-1"))
        except (ValueError, zlib.error):
            continue
    return "".join(partes)


class ReportePdfTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.admin = crear_usuario("ADMINISTRADOR")
        self.efectivo = MetodoPago.objects.create(nombre="Efectivo")
        orden = Orden.objects.create(mesa=self.d["mesa"], sucursal=self.d["centro"], estado=Orden.ENTREGADA)
        DetalleOrden.objects.create(orden=orden, producto=self.d["bandeja"], cantidad=2, precio_unitario=Decimal("32000"))
        Pago.objects.create(orden=orden, metodo_pago=self.efectivo, monto=Decimal("64000"), propina=Decimal("5000"))

        otro = Restaurante.objects.create(nombre="Ajeno", nif="800999111", email="a@ajeno.co", direccion="x")
        sucursal = Sucursal.objects.create(restaurante=otro, nombre="Única")
        ajena = Orden.objects.create(sucursal=sucursal, estado=Orden.ENTREGADA)
        Pago.objects.create(orden=ajena, metodo_pago=self.efectivo, monto=Decimal("999000"))

    def test_la_web_descarga_el_pdf_del_restaurante(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("reportes:reporte_pdf"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertTrue(r.content.startswith(b"%PDF"))
        texto = texto_del_pdf(r.content)
        self.assertIn("$64.000", texto)
        self.assertIn("Bandeja paisa", texto)
        self.assertNotIn("$999.000", texto)

    def test_la_pagina_de_reportes_muestra_el_formulario(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("reportes:reportes"))
        self.assertContains(r, "Descargar reporte en PDF")
        self.assertContains(r, reverse("reportes:reporte_pdf"))

    def test_fechas_invalidas_vuelven_a_reportes_con_mensaje(self):
        self.client.force_login(self.admin)
        hoy = timezone.localdate()
        r = self.client.get(reverse("reportes:reporte_pdf"), {"desde": hoy.isoformat(), "hasta": (hoy - timedelta(days=1)).isoformat()})
        self.assertRedirects(r, reverse("reportes:reportes"))

    def test_un_periodo_sin_ventas_tambien_genera_pdf(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("reportes:reporte_pdf"), {"desde": "2020-01-01", "hasta": "2020-01-31"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("No hubo pagos aprobados", texto_del_pdf(r.content))

    def test_el_cajero_no_descarga_reportes_en_la_web(self):
        self.client.force_login(crear_usuario("CAJERO"))
        self.assertEqual(self.client.get(reverse("reportes:reporte_pdf")).status_code, 403)

    def test_la_api_descarga_el_pdf_para_la_app(self):
        r = api_de(self.admin).get(reverse("api:g_reporte_pdf"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_la_api_rechaza_fechas_invalidas(self):
        r = api_de(self.admin).get(reverse("api:g_reporte_pdf"), {"desde": "ayer"})
        self.assertEqual(r.status_code, 400)

    def test_la_api_no_deja_al_cajero(self):
        self.assertEqual(api_de(crear_usuario("CAJERO")).get(reverse("api:g_reporte_pdf")).status_code, 403)
