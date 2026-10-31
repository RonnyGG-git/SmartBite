from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalogo.models import Producto
from core.testing import crear_escenario, crear_usuario
from inventario.models import ItemInventario, MovimientoInventario
from inventario.services import calcular_insumos_requeridos, descontar_insumos_por_receta
from operativo.models import DetalleOrden, Mesa, Orden, TransicionOrdenInvalida
from recetas.models import ProductoIngrediente


class TransicionesOrdenTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.mesa = self.d["mesa"]
        self.mesa.estado = Mesa.OCUPADA
        self.mesa.save(update_fields=["estado"])
        self.orden = Orden.objects.create(mesa=self.mesa)

    def test_transiciones_permitidas(self):
        self.assertTrue(self.orden.puede_cambiar_a(Orden.EN_PREPARACION))
        self.assertTrue(self.orden.puede_cambiar_a(Orden.CANCELADA))
        self.assertFalse(self.orden.puede_cambiar_a(Orden.LISTA))
        self.assertFalse(self.orden.puede_cambiar_a(Orden.ENTREGADA))
        self.assertEqual(
            self.orden.transiciones_disponibles, [Orden.EN_PREPARACION, Orden.CANCELADA]
        )

    def test_transicion_invalida_es_rechazada_y_no_persiste(self):
        with self.assertRaises(TransicionOrdenInvalida):
            self.orden.cambiar_estado(Orden.ENTREGADA)

        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)

    def test_transicion_invalida_es_un_validation_error(self):
        with self.assertRaises(ValidationError) as ctx:
            self.orden.cambiar_estado(Orden.ENTREGADA)
        self.assertEqual(ctx.exception.code, "transicion_invalida")

    def test_paso_completo_hasta_entregada(self):
        self.orden.cambiar_estado(Orden.EN_PREPARACION)
        self.orden.cambiar_estado(Orden.LISTA)
        self.orden.cambiar_estado(Orden.ENTREGADA)

        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.ENTREGADA)
        self.assertTrue(self.orden.es_final)

    def test_cancelar_desde_pendiente_libera_la_mesa(self):
        self.orden.cambiar_estado(Orden.CANCELADA)

        self.orden.refresh_from_db()
        self.mesa.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.CANCELADA)
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)

    def test_entregar_libera_la_mesa(self):
        self.orden.cambiar_estado(Orden.EN_PREPARACION)
        self.orden.cambiar_estado(Orden.LISTA)
        self.orden.cambiar_estado(Orden.ENTREGADA)

        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)

    def test_entrar_a_preparacion_ocupa_la_mesa(self):
        self.mesa.estado = Mesa.DISPONIBLE
        self.mesa.save(update_fields=["estado"])

        self.orden.cambiar_estado(Orden.EN_PREPARACION)

        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.OCUPADA)

    def test_estado_final_no_admite_mas_transiciones(self):
        self.orden.cambiar_estado(Orden.CANCELADA)
        self.orden.refresh_from_db()

        self.assertEqual(self.orden.transiciones_disponibles, [])
        with self.assertRaises(TransicionOrdenInvalida):
            self.orden.cambiar_estado(Orden.EN_PREPARACION)

    def test_campos_extra_se_guardan_en_la_misma_operacion(self):
        ahora = timezone.now()
        self.orden.cambiar_estado(
            Orden.EN_PREPARACION,
            tiempo_estimado_min=20,
            preparacion_iniciada_en=ahora,
        )

        self.orden.refresh_from_db()
        self.assertEqual(self.orden.tiempo_estimado_min, 20)
        self.assertEqual(self.orden.preparacion_iniciada_en, ahora)


class DescuentoPorRecetaTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.orden = Orden.objects.create(mesa=self.d["mesa"])
        DetalleOrden.objects.create(
            orden=self.orden, producto=self.d["bandeja"], cantidad=3, precio_unitario=Decimal("32000")
        )
        self.frijol = ItemInventario.objects.create(
            nombre="Frijol", stock_actual=100, sucursal=self.d["centro"]
        )
        self.arroz = ItemInventario.objects.create(
            nombre="Arroz", stock_actual=100, sucursal=self.d["centro"]
        )
        ProductoIngrediente.objects.create(
            producto=self.d["bandeja"], item_inventario=self.frijol, cantidad_requerida=Decimal("0.250")
        )
        ProductoIngrediente.objects.create(
            producto=self.d["bandeja"], item_inventario=self.arroz, cantidad_requerida=Decimal("1.000")
        )

    def test_calcula_requerimiento_agregando_receta_por_cantidad(self):
        requerido = calcular_insumos_requeridos(self.orden)
        self.assertEqual(requerido[self.frijol], Decimal("0.750"))
        self.assertEqual(requerido[self.arroz], Decimal("3.000"))

    def test_descuenta_con_ceil_al_entrar_en_preparacion(self):
        self.orden.cambiar_estado(Orden.EN_PREPARACION)

        self.frijol.refresh_from_db()
        self.arroz.refresh_from_db()
        self.assertEqual(self.frijol.stock_actual, 99)
        self.assertEqual(self.arroz.stock_actual, 97)

    def test_registra_un_movimiento_salida_por_ingrediente(self):
        self.orden.cambiar_estado(Orden.EN_PREPARACION)

        movimientos = MovimientoInventario.objects.select_related("item").order_by("item__nombre")
        self.assertEqual(movimientos.count(), 2)
        for movimiento in movimientos:
            self.assertEqual(movimiento.tipo, MovimientoInventario.SALIDA)
            self.assertEqual(movimiento.motivo, f"Orden #{self.orden.pk}")

    def test_ingrediente_inactivo_no_se_descuenta(self):
        ingrediente = ProductoIngrediente.objects.get(item_inventario=self.frijol)
        ingrediente.activo = False
        ingrediente.save(update_fields=["activo"])

        self.orden.cambiar_estado(Orden.EN_PREPARACION)

        self.frijol.refresh_from_db()
        self.assertEqual(self.frijol.stock_actual, 100)

    def test_platillo_sin_receta_no_descuenta_nada(self):
        ProductoIngrediente.objects.all().delete()

        self.orden.cambiar_estado(Orden.EN_PREPARACION)

        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_solo_descuenta_una_vez_por_transicion(self):
        self.orden.cambiar_estado(Orden.EN_PREPARACION)
        self.orden.cambiar_estado(Orden.LISTA)
        self.orden.refresh_from_db()

        self.arroz.refresh_from_db()
        self.assertEqual(self.arroz.stock_actual, 97)
        self.assertEqual(MovimientoInventario.objects.count(), 2)

    def test_otros_detalles_de_la_misma_orden_comparten_el_mismo_item(self):
        otro = Producto.objects.create(
            nombre="Sancocho",
            precio=Decimal("25000"),
            categoria=self.d["categoria"],
            sucursal=self.d["centro"],
        )
        ProductoIngrediente.objects.create(
            producto=otro, item_inventario=self.frijol, cantidad_requerida=Decimal("0.250")
        )
        DetalleOrden.objects.create(
            orden=self.orden, producto=otro, cantidad=1, precio_unitario=Decimal("25000")
        )

        self.orden.cambiar_estado(Orden.EN_PREPARACION)

        self.frijol.refresh_from_db()
        self.assertEqual(self.frijol.stock_actual, 99)
        frijol_movimientos = MovimientoInventario.objects.filter(item=self.frijol)
        self.assertEqual(frijol_movimientos.count(), 1)
        self.assertEqual(frijol_movimientos.get().cantidad, 1)

    def test_stock_insuficiente_recorta_y_reporta_el_faltante(self):
        self.frijol.stock_actual = 0
        self.frijol.save(update_fields=["stock_actual"])

        resultado = descontar_insumos_por_receta(self.orden)

        self.frijol.refresh_from_db()
        self.assertEqual(self.frijol.stock_actual, 0)
        self.assertEqual(resultado["faltantes"][self.frijol], 1)

    def test_el_faltante_queda_expuesto_en_la_orden(self):
        self.frijol.stock_actual = 0
        self.frijol.save(update_fields=["stock_actual"])

        self.orden.cambiar_estado(Orden.EN_PREPARACION)

        self.assertIn(self.frijol, self.orden.insumos_faltantes)

    def test_sin_faltantes_el_orden_no_tiene_pendientes(self):
        self.orden.cambiar_estado(Orden.EN_PREPARACION)
        self.assertEqual(self.orden.insumos_faltantes, {})


class CocinaDescuentaInventarioTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.orden = Orden.objects.create(mesa=self.d["mesa"])
        DetalleOrden.objects.create(
            orden=self.orden, producto=self.d["bandeja"], cantidad=2, precio_unitario=Decimal("32000")
        )
        self.item = ItemInventario.objects.create(
            nombre="Chorizo", stock_actual=10, sucursal=self.d["centro"]
        )
        ProductoIngrediente.objects.create(
            producto=self.d["bandeja"], item_inventario=self.item, cantidad_requerida=Decimal("1.500")
        )
        self.client.force_login(crear_usuario("JEFE_COCINA"))

    def test_la_vista_descuenta_al_iniciar(self):
        self.client.post(
            reverse("cocina:actualizar_estado", args=[self.orden.pk]),
            {"accion": "iniciar", "tiempo_estimado": 20},
        )

        self.item.refresh_from_db()
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.EN_PREPARACION)
        self.assertEqual(self.item.stock_actual, 7)
        self.assertEqual(MovimientoInventario.objects.get().motivo, f"Orden #{self.orden.pk}")

    def test_la_vista_no_descuenta_al_marcar_lista(self):
        self.client.post(
            reverse("cocina:actualizar_estado", args=[self.orden.pk]),
            {"accion": "iniciar", "tiempo_estimado": 20},
        )
        self.client.post(
            reverse("cocina:actualizar_estado", args=[self.orden.pk]), {"accion": "listo"}
        )

        self.item.refresh_from_db()
        self.assertEqual(self.item.stock_actual, 7)
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_una_accion_invalida_no_descuenta(self):
        self.client.post(
            reverse("cocina:actualizar_estado", args=[self.orden.pk]), {"accion": "listo"}
        )

        self.orden.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.orden.estado, Orden.PENDIENTE)
        self.assertEqual(self.item.stock_actual, 10)
        self.assertEqual(MovimientoInventario.objects.count(), 0)
