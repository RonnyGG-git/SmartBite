from decimal import Decimal

from django.urls import reverse

from operativo.models import DetalleOrden, Mesa, Orden

from .base import CasoDeUsoTestCase


class FlujoPedidosTests(CasoDeUsoTestCase):
    def sin_mesa(self, estado=Orden.POR_CONFIRMAR, tipo=Orden.PARA_LLEVAR):
        orden = Orden.objects.create(
            sucursal=self.sucursal, origen=Orden.ORIGEN_AUTOPEDIDO, tipo_consumo=tipo, estado=estado
        )
        DetalleOrden.objects.create(orden=orden, producto=self.hamburguesa, cantidad=1, precio_unitario=Decimal("20000"))
        return orden

    def cobrar(self, orden, monto="20000"):
        return self.client.post(
            reverse("caja:cobrar_orden", args=[orden.pk]),
            {"metodo_pago": self.efectivo.pk, "monto": monto, "referencia_transaccion": ""},
        )

    def en_cocina(self, orden):
        self.entrar_como("JEFE_COCINA")
        visible = orden in self.client.get(reverse("cocina:cocina")).context["ordenes"]
        self.entrar_como("CAJERO")
        return visible

    def test_directorio_crea_pedido_por_confirmar_que_no_llega_a_cocina(self):
        self.client.get(reverse("cliente:sucursal", args=[self.sucursal.pk]))
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": Orden.PARA_LLEVAR})
        datos = {f"cant_{self.gaseosa.pk}": 2, "nombre": "Laura"}
        self.client.post(reverse("cliente:carrito"), datos)
        self.client.post(reverse("cliente:autopedido"), datos)
        orden = Orden.objects.get()
        self.assertEqual(orden.estado, Orden.POR_CONFIRMAR)
        self.entrar_como("CAJERO")
        self.assertFalse(self.en_cocina(orden))
        self.assertContains(self.client.get(reverse("caja:para_llevar")), f"#{orden.pk}")

    def test_caja_acepta_y_el_pedido_pasa_a_cocina(self):
        orden = self.sin_mesa()
        self.entrar_como("CAJERO")
        self.client.post(reverse("caja:aceptar_orden", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.assertTrue(self.en_cocina(orden))

    def test_caja_rechaza_y_nunca_llega_a_cocina(self):
        orden = self.sin_mesa()
        self.entrar_como("CAJERO")
        self.client.post(reverse("caja:rechazar_orden", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.CANCELADA)
        self.assertFalse(self.en_cocina(orden))

    def test_solo_se_rechazan_pedidos_por_confirmar(self):
        orden = self.sin_mesa(estado=Orden.PENDIENTE)
        self.entrar_como("CAJERO")
        self.client.post(reverse("caja:rechazar_orden", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.PENDIENTE)

    def test_prepago_acepta_el_pedido_y_luego_se_entrega_sin_volver_a_cobrar(self):
        orden = self.sin_mesa()
        self.entrar_como("CAJERO")
        self.assertRedirects(self.cobrar(orden), reverse("caja:para_llevar"))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.assertTrue(orden.pagada)
        orden.cambiar_estado(Orden.EN_PREPARACION)
        orden.cambiar_estado(Orden.LISTA)
        self.client.post(reverse("caja:entregar_orden", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.ENTREGADA)
        self.assertEqual(orden.pagos.count(), 1)

    def test_no_se_entrega_un_pedido_sin_pagar(self):
        orden = self.sin_mesa(estado=Orden.LISTA)
        self.entrar_como("CAJERO")
        respuesta = self.client.post(reverse("caja:entregar_orden", args=[orden.pk]))
        self.assertRedirects(respuesta, reverse("caja:cobrar_orden", args=[orden.pk]))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.LISTA)

    def test_paga_al_recoger_cobra_y_entrega_en_un_paso(self):
        orden = self.sin_mesa(estado=Orden.LISTA)
        self.entrar_como("CAJERO")
        self.assertRedirects(self.cobrar(orden), reverse("caja:ventas_list"))
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.ENTREGADA)

    def test_mesa_sigue_igual_va_directo_a_cocina_y_se_cobra_en_lista(self):
        orden = self.crear_orden(estado=Orden.PENDIENTE)
        self.entrar_como("CAJERO")
        self.assertTrue(self.en_cocina(orden))
        self.cobrar(orden, monto="10000")
        orden.refresh_from_db()
        self.assertFalse(orden.pagos.exists())
        Orden.objects.filter(pk=orden.pk).update(estado=Orden.LISTA)
        orden.refresh_from_db()
        self.cobrar(orden, monto="10000")
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.ENTREGADA)
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)

    def test_qr_en_mesa_va_directo_a_cocina(self):
        self.escanear_qr()
        datos = {f"cant_{self.gaseosa.pk}": 1, "nombre": ""}
        self.client.post(reverse("cliente:carrito"), datos)
        self.client.post(reverse("cliente:autopedido"), datos)
        orden = Orden.objects.get()
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.assertEqual(orden.mesa, self.mesa)

    def test_ventas_incluye_prepagos_aun_en_cocina(self):
        orden = self.sin_mesa()
        self.entrar_como("CAJERO")
        self.cobrar(orden)
        self.assertContains(self.client.get(reverse("caja:ventas_list")), f"#{orden.pk}")

    def test_detalle_por_confirmar_muestra_aceptar_y_rechazar(self):
        orden = self.sin_mesa()
        self.entrar_como("CAJERO")
        respuesta = self.client.get(reverse("operativo:detalle_orden", args=[orden.pk]))
        self.assertContains(respuesta, reverse("caja:aceptar_orden", args=[orden.pk]))
        self.assertContains(respuesta, reverse("caja:rechazar_orden", args=[orden.pk]))
        self.assertContains(respuesta, "Aceptar y cobrar")

    def test_detalle_pagada_y_lista_muestra_entregar(self):
        orden = self.sin_mesa()
        self.entrar_como("CAJERO")
        self.cobrar(orden)
        Orden.objects.filter(pk=orden.pk).update(estado=Orden.LISTA)
        respuesta = self.client.get(reverse("operativo:detalle_orden", args=[orden.pk]))
        self.assertContains(respuesta, reverse("caja:entregar_orden", args=[orden.pk]))
        self.assertNotContains(respuesta, reverse("caja:cobrar_orden", args=[orden.pk]))
