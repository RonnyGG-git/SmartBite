from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.testing import crear_escenario
from inventario.models import ItemInventario, MovimientoInventario


class AjustarStockTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.item = ItemInventario.objects.create(
            nombre="Arroz", stock_actual=10, stock_minimo=2, sucursal=self.d["centro"]
        )

    def test_entrada_suma_y_registra_movimiento(self):
        movimiento = self.item.ajustar_stock(MovimientoInventario.ENTRADA, 5, "Compra")

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 15)
        self.assertEqual(MovimientoInventario.objects.count(), 1)
        self.assertEqual(movimiento.tipo, MovimientoInventario.ENTRADA)
        self.assertEqual(movimiento.cantidad, 5)
        self.assertEqual(movimiento.motivo, "Compra")

    def test_salida_resta(self):
        self.item.ajustar_stock(MovimientoInventario.SALIDA, 4, "Cocina")

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 6)
        self.assertEqual(MovimientoInventario.objects.get().tipo, MovimientoInventario.SALIDA)

    def test_perdida_se_comporta_exactamente_igual_que_salida(self):
        self.item.ajustar_stock(MovimientoInventario.PERDIDA, 4, "Merma")

        self.item.refresh_from_db()
        movimiento = MovimientoInventario.objects.get()
        self.assertEqual(self.item.stock_actual, 6)
        self.assertEqual(movimiento.tipo, MovimientoInventario.PERDIDA)
        self.assertEqual(movimiento.cantidad, 4)

    def test_perdida_no_baja_de_cero(self):
        self.item.ajustar_stock(MovimientoInventario.PERDIDA, 999, "Merma total")

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 0)

    def test_salida_no_baja_de_cero(self):
        self.item.ajustar_stock(MovimientoInventario.SALIDA, 999, "Consumo")

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 0)

    def test_tipo_desconocido_es_rechazado(self):
        with self.assertRaises(ValidationError):
            self.item.ajustar_stock("BAJA", 1, "x")
        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 10)
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_cantidad_no_positiva_es_rechazada(self):
        with self.assertRaises(ValidationError):
            self.item.ajustar_stock(MovimientoInventario.SALIDA, 0, "x")
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_nuevos_campos_del_item(self):
        self.item.fecha_vencimiento = date(2026, 12, 31)
        self.item.categoria = "Granos"
        self.item.activo = False
        self.item.save()

        self.item.refresh_from_db()
        self.assertEqual(self.item.fecha_vencimiento, date(2026, 12, 31))
        self.assertEqual(self.item.categoria, "Granos")
        self.assertFalse(self.item.activo)

    def test_activo_por_defecto(self):
        nuevo = ItemInventario.objects.create(nombre="Sal", sucursal=self.d["centro"])
        self.assertTrue(nuevo.activo)
        self.assertIsNone(nuevo.fecha_vencimiento)
        self.assertEqual(nuevo.categoria, "")
