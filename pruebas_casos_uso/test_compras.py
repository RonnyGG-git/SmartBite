from django.urls import reverse

from inventario.models import Compra, DetalleCompra, MovimientoInventario, Proveedor

from .base import CasoDeUsoTestCase


class ComprasTests(CasoDeUsoTestCase):

    def setUp(self):
        self.entrar_como("JEFE_INVENTARIO")
        self.proveedor = Proveedor.objects.create(nombre="Panadería La Espiga", restaurante=self.restaurante)

    def compra_pendiente(self, cantidad=20):
        compra = Compra.objects.create(proveedor=self.proveedor)
        DetalleCompra.objects.create(compra=compra, item=self.pan, cantidad=cantidad, costo_unitario=800)
        return compra

    def test_cu_com_11_generar_orden_de_compra(self):
        self.client.post(reverse("inventario:compra_crear"), {
            "proveedor": self.proveedor.pk,
            "detalles-TOTAL_FORMS": "1", "detalles-INITIAL_FORMS": "0",
            "detalles-MIN_NUM_FORMS": "0", "detalles-MAX_NUM_FORMS": "1000",
            "detalles-0-item": self.pan.pk, "detalles-0-cantidad": "12", "detalles-0-costo_unitario": "800",
        })
        compra = Compra.objects.get()
        self.assertEqual((compra.estado, compra.detalles.get().cantidad), (Compra.PENDIENTE, 12))

    def test_cu_com_13_recibir_productos_entregados(self):
        compra = self.compra_pendiente()
        url = reverse("inventario:compra_recibir", args=[compra.pk])
        self.client.post(url)
        self.client.post(url)
        compra.refresh_from_db()
        self.pan.refresh_from_db()
        self.assertEqual((compra.estado, self.pan.stock_actual), (Compra.RECIBIDA, 30))
        self.assertEqual(MovimientoInventario.objects.get().motivo, f"Recepción compra #{compra.pk}")

    def test_cu_com_20_consultar_historial_de_compras(self):
        recibida = self.compra_pendiente()
        self.client.post(reverse("inventario:compra_recibir", args=[recibida.pk]))
        anulada = self.compra_pendiente()
        self.client.post(reverse("inventario:compra_anular", args=[anulada.pk]))
        compras = {c.pk: c.estado for c in self.client.get(reverse("inventario:compras_list")).context["compras"]}
        self.assertEqual(compras, {recibida.pk: Compra.RECIBIDA, anulada.pk: Compra.ANULADA})
