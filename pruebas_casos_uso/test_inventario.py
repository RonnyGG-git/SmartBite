from django.urls import reverse

from inventario.models import Compra, DetalleCompra, ItemInventario, MovimientoInventario, Proveedor
from operativo.models import Orden

from .base import CasoDeUsoTestCase


class InventarioTests(CasoDeUsoTestCase):

    def setUp(self):
        self.entrar_como("JEFE_INVENTARIO")

    def ajustar(self, tipo, cantidad, motivo="Conteo"):
        return self.client.post(
            reverse("inventario:item_ajustar", args=[self.pan.pk]),
            {"tipo": tipo, "cantidad": cantidad, "motivo": motivo},
        )

    def test_cu_inv_01_registrar_producto(self):
        self.client.post(reverse("inventario:item_crear"), {
            "nombre": "Queso", "unidad_medida": "kg", "stock_actual": 5, "stock_minimo": 1,
            "costo_unitario": "12000", "sucursal": self.sucursal.pk,
        })
        self.assertTrue(ItemInventario.objects.filter(nombre="Queso").exists())

    def test_cu_inv_02_consultar_inventario(self):
        self.entrar_como("JEFE_COCINA")
        respuesta = self.client.get(reverse("inventario:inventario_list"))
        self.assertIn(self.pan, list(respuesta.context["items"]))
        self.assertFalse(respuesta.context["puede_gestionar"])
        self.entrar_como("MESERO")
        self.assertEqual(self.client.get(reverse("inventario:inventario_list")).status_code, 403)

    def test_cu_inv_03_actualizar_producto(self):
        self.client.post(reverse("inventario:item_editar", args=[self.pan.pk]), {
            "nombre": "Pan brioche", "unidad_medida": "unidad", "stock_actual": 10, "stock_minimo": 3,
            "costo_unitario": "800", "sucursal": self.sucursal.pk,
        })
        self.pan.refresh_from_db()
        self.assertEqual((self.pan.nombre, self.pan.stock_minimo), ("Pan brioche", 3))

    def test_cu_inv_04_controlar_existencias(self):
        self.assertFalse(self.pan.stock_bajo)
        self.ajustar("SALIDA", 8)
        self.pan.refresh_from_db()
        self.assertTrue(self.pan.stock_bajo)

    def test_cu_inv_05_registrar_entrada_de_inventario(self):
        self.ajustar("ENTRADA", 5, "Donación")
        self.pan.refresh_from_db()
        self.assertEqual(self.pan.stock_actual, 15)

    def test_cu_inv_06_registrar_salida_de_inventario(self):
        self.ajustar("SALIDA", 50)
        self.pan.refresh_from_db()
        self.assertEqual(self.pan.stock_actual, 0)

    def test_cu_inv_07_consultar_movimientos_de_inventario(self):
        self.ajustar("ENTRADA", 1)
        movimientos = self.client.get(reverse("inventario:movimientos_list")).context["movimientos"]
        self.assertEqual([m.tipo for m in movimientos], [MovimientoInventario.ENTRADA])

    def test_cu_inv_08_realizar_ajuste_de_inventario(self):
        self.ajustar("SALIDA", 0)
        self.assertFalse(MovimientoInventario.objects.exists())
        self.entrar_como("JEFE_COCINA")
        self.ajustar("ENTRADA", 3)
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_cu_inv_10_registrar_perdida_de_producto(self):
        movimiento = self.pan.ajustar_stock(MovimientoInventario.PERDIDA, 2, "Pan vencido")
        self.assertEqual((movimiento.tipo, self.pan.stock_actual), (MovimientoInventario.PERDIDA, 8))

    def test_cu_inv_11_consultar_stock_minimo(self):
        self.pan.stock_actual = 3
        self.assertFalse(self.pan.stock_bajo)
        self.pan.stock_actual = 2
        self.assertTrue(self.pan.stock_bajo)

    def test_cu_inv_12_generar_reporte_de_inventario(self):
        self.pan.ajustar_stock(MovimientoInventario.SALIDA, 9, "Consumo")
        self.entrar_como("ADMINISTRADOR")
        self.assertEqual(self.client.get(reverse("reportes:dashboard")).context["items_stock_bajo"], [self.pan])

    def test_cu_inv_14_consultar_stock_disponible(self):
        orden = self.crear_orden(items=[(self.hamburguesa, 3)])
        orden.cambiar_estado(Orden.EN_PREPARACION)
        self.pan.refresh_from_db()
        self.assertEqual(self.pan.stock_actual, 7)

    def test_cu_inv_15_enviar_solicitud_de_reabastecimiento(self):
        proveedor = Proveedor.objects.create(nombre="Panadería", restaurante=self.restaurante)
        compra = Compra.objects.create(proveedor=proveedor)
        DetalleCompra.objects.create(compra=compra, item=self.pan, cantidad=20, costo_unitario=800)
        self.assertEqual(compra.estado, Compra.PENDIENTE)
        self.assertEqual(compra.total, 16000)

    def test_cu_inv_17_registrar_movimiento_de_inventario(self):
        orden = self.crear_orden(items=[(self.hamburguesa, 2)])
        orden.cambiar_estado(Orden.EN_PREPARACION)
        movimiento = MovimientoInventario.objects.get()
        self.assertEqual(
            (movimiento.item, movimiento.tipo, movimiento.cantidad, movimiento.motivo),
            (self.pan, MovimientoInventario.SALIDA, 2, f"Orden #{orden.pk}"),
        )
