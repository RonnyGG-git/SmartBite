from datetime import timedelta
from decimal import Decimal

from django.urls import reverse

from catalogo.models import Producto
from cliente.forms import MAX_CANTIDAD_POR_PRODUCTO
from cliente.models import Retroalimentacion
from cliente.views import SESION_MESA, SESION_PEDIDOS
from cocina.views import insumos_faltantes
from operativo.models import Mesa, Orden

from .base import CasoDeUsoTestCase


class PedidosTests(CasoDeUsoTestCase):

    def autopedir(self, *pares):
        datos = {f"cant_{producto.pk}": cantidad for producto, cantidad in pares}
        return self.client.post(reverse("cliente:autopedido"), datos)


    def test_cu_ped_01_consultar_menu_disponible(self):
        Producto.objects.create(
            nombre="Jugo agotado", precio=Decimal("4000"), categoria=self.bebidas,
            sucursal=self.sucursal, disponible=False,
        )
        Producto.objects.create(
            nombre="Gaseosa Norte", precio=Decimal("5000"), categoria=self.bebidas,
            sucursal=self.otra_sucursal,
        )
        self.escanear_qr()
        respuesta = self.client.get(reverse("cliente:menu"))
        productos = [p for _, lista in respuesta.context["categorias"] for p in lista]
        self.assertCountEqual(productos, [self.gaseosa, self.hamburguesa])
        self.assertEqual([c for c, _ in respuesta.context["categorias"]], [self.bebidas, self.platos])

    def test_cu_ped_02_seleccionar_platillos(self):
        self.escanear_qr()
        self.autopedir((self.gaseosa, 3), (self.hamburguesa, 99))
        orden = Orden.objects.get()
        cantidades = {d.producto: d.cantidad for d in orden.detalles.all()}
        self.assertEqual(cantidades, {self.gaseosa: 3, self.hamburguesa: MAX_CANTIDAD_POR_PRODUCTO})

    def test_cu_ped_05_realizar_autopedido(self):
        self.escanear_qr()
        respuesta = self.autopedir((self.gaseosa, 1))
        orden = Orden.objects.get()
        self.assertEqual(orden.origen, Orden.ORIGEN_AUTOPEDIDO)
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.assertIn(orden.pk, self.client.session[SESION_PEDIDOS])
        self.assertRedirects(respuesta, reverse("cliente:pedido", args=[orden.pk]))

    def test_cu_ped_05_autopedido_sin_platillos_no_crea_orden(self):
        self.escanear_qr()
        self.autopedir()
        self.assertFalse(Orden.objects.exists())

    def test_cu_ped_13_consultar_estado_del_pedido(self):
        self.escanear_qr()
        self.autopedir((self.gaseosa, 1))
        orden = Orden.objects.get()
        self.assertEqual(self.client.get(reverse("cliente:pedido", args=[orden.pk])).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("cliente:pedido", args=[orden.pk])).status_code, 404)

    def test_cu_ped_16_escanear_codigo_qr_de_mesa(self):
        respuesta = self.escanear_qr()
        self.assertRedirects(respuesta, reverse("cliente:tipo_consumo"))
        self.assertEqual(self.client.session[SESION_MESA], self.mesa.pk)
        Mesa.objects.filter(pk=self.mesa.pk).update(activa=False)
        self.assertEqual(self.escanear_qr().status_code, 404)

    def test_cu_ped_16_qr_impresos_antiguos_redirigen(self):
        respuesta = self.client.get(reverse("menu_cliente:menu"), {"mesa": self.mesa.pk})
        self.assertRedirects(respuesta, reverse("cliente:mesa", args=[self.mesa.pk]), fetch_redirect_response=False)

    def test_cu_ped_17_enviar_retroalimentacion(self):
        self.escanear_qr()
        self.client.post(reverse("cliente:retroalimentacion"), {"tipo": "SUGERENCIA", "mensaje": "Todo bien"})
        self.assertEqual(Retroalimentacion.objects.get().mesa, self.mesa)

    def test_cu_ped_18_enviar_sugerencia(self):
        self.client.post(reverse("cliente:retroalimentacion"), {"tipo": "SUGERENCIA", "mensaje": "Más postres"})
        self.assertEqual(Retroalimentacion.objects.get().tipo, Retroalimentacion.SUGERENCIA)

    def test_cu_ped_19_registrar_denuncia(self):
        self.client.post(reverse("cliente:retroalimentacion"), {"tipo": "DENUNCIA", "mensaje": "Mala atención"})
        self.assertEqual(Retroalimentacion.objects.get().tipo, Retroalimentacion.DENUNCIA)


    def test_cu_ped_03_registrar_pedido_en_mesa(self):
        self.entrar_como("MESERO")
        respuesta = self.client.post(reverse("operativo:crear_orden"), {"mesa": self.mesa.pk, "cliente": ""})
        orden = Orden.objects.get()
        self.assertEqual(orden.origen, Orden.ORIGEN_MESERO)
        self.assertRedirects(respuesta, reverse("operativo:detalle_orden", args=[orden.pk]))

    def test_cu_ped_04_asignar_mesa_a_cliente(self):
        self.entrar_como("MESERO")
        self.client.post(reverse("operativo:crear_orden"), {"mesa": self.mesa.pk, "cliente": ""})
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.OCUPADA)
        self.client.post(reverse("operativo:crear_orden"), {"mesa": self.mesa.pk, "cliente": ""})
        self.assertEqual(Orden.objects.count(), 1)

    def test_cu_ped_06_modificar_pedido(self):
        self.entrar_como("MESERO")
        orden = self.crear_orden()
        url = reverse("operativo:agregar_producto", args=[orden.pk])
        self.client.post(url, {"producto": self.hamburguesa.pk, "cantidad": 1})
        self.assertEqual(orden.detalles.count(), 2)
        Orden.objects.filter(pk=orden.pk).update(estado=Orden.EN_PREPARACION)
        self.client.post(url, {"producto": self.hamburguesa.pk, "cantidad": 1})
        self.assertEqual(orden.detalles.count(), 2)

    def test_cu_ped_07_cancelar_pedido(self):
        self.entrar_como("MESERO")
        orden = self.crear_orden()
        self.client.post(reverse("operativo:cambiar_estado_orden", args=[orden.pk]), {"estado": Orden.CANCELADA})
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.CANCELADA)

    def test_cu_ped_07_no_se_cancela_un_pedido_en_preparacion(self):
        self.entrar_como("MESERO")
        orden = self.crear_orden(estado=Orden.EN_PREPARACION)
        self.client.post(reverse("operativo:cambiar_estado_orden", args=[orden.pk]), {"estado": Orden.CANCELADA})
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.EN_PREPARACION)

    def test_cu_ped_14_solicitar_cuenta(self):
        self.entrar_como("MESERO")
        pendiente = self.crear_orden()
        self.client.post(reverse("operativo:solicitar_cuenta", args=[pendiente.pk]))
        pendiente.refresh_from_db()
        self.assertIsNone(pendiente.cuenta_solicitada_en)
        Orden.objects.filter(pk=pendiente.pk).update(estado=Orden.LISTA)
        self.client.post(reverse("operativo:solicitar_cuenta", args=[pendiente.pk]))
        pendiente.refresh_from_db()
        self.assertIsNotNone(pendiente.cuenta_solicitada_en)

    def test_cu_ped_20_consultar_pedidos_pendientes(self):
        self.entrar_como("MESERO")
        orden = self.crear_orden()
        mesas = self.client.get(reverse("operativo:mesas_list")).context["mesas"]
        self.assertEqual(mesas.get(pk=self.mesa.pk).orden_activa, orden)

    def test_cu_ped_21_desasignar_mesa_a_cliente(self):
        orden = self.crear_orden()
        orden.cambiar_estado(Orden.CANCELADA)
        self.mesa.refresh_from_db()
        self.assertEqual(self.mesa.estado, Mesa.DISPONIBLE)


    def test_cu_ped_08_enviar_pedido_a_cocina(self):
        self.escanear_qr()
        self.autopedir((self.gaseosa, 1))
        self.client.logout()
        self.entrar_como("JEFE_COCINA")
        cola = self.client.get(reverse("cocina:cocina")).context["ordenes"]
        self.assertIn(Orden.objects.get(), list(cola))

    def test_cu_ped_09_consultar_pedidos_en_cola(self):
        pendiente = self.crear_orden()
        lista = self.crear_orden(estado=Orden.LISTA)
        self.entrar_como("JEFE_COCINA")
        cola = list(self.client.get(reverse("cocina:cocina")).context["ordenes"])
        self.assertIn(pendiente, cola)
        self.assertNotIn(lista, cola)
        self.entrar_como("MESERO")
        self.assertEqual(self.client.get(reverse("cocina:cocina")).status_code, 403)

    def test_cu_ped_10_actualizar_estado_de_preparacion(self):
        orden = self.crear_orden()
        self.entrar_como("JEFE_COCINA")
        url = reverse("cocina:actualizar_estado", args=[orden.pk])
        self.client.post(url, {"accion": "iniciar", "tiempo_estimado": "0"})
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.PENDIENTE)
        self.client.post(url, {"accion": "iniciar", "tiempo_estimado": "15"})
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.EN_PREPARACION)

    def test_cu_ped_11_confirmar_pedido_listo(self):
        orden = self.crear_orden(estado=Orden.EN_PREPARACION)
        self.entrar_como("JEFE_COCINA")
        self.client.post(reverse("cocina:actualizar_estado", args=[orden.pk]), {"accion": "listo"})
        orden.refresh_from_db()
        self.assertEqual(orden.estado, Orden.LISTA)

    def test_cu_ped_12_reportar_insumo_faltante(self):
        orden = self.crear_orden(items=[(self.hamburguesa, 11)])
        self.entrar_como("JEFE_COCINA")
        cola = self.client.get(reverse("cocina:cocina")).context["ordenes"]
        self.assertEqual(next(o for o in cola if o.pk == orden.pk).faltantes, [self.pan])

    def test_cu_ped_22_verificar_disponibilidad_de_ingredientes(self):
        self.assertEqual(insumos_faltantes(self.crear_orden(items=[(self.hamburguesa, 10)])), [])
        self.assertEqual(insumos_faltantes(self.crear_orden(items=[(self.hamburguesa, 11)])), [self.pan])

    def test_cu_ped_23_establecer_tiempo_estimado_de_preparacion(self):
        orden = self.crear_orden()
        self.entrar_como("JEFE_COCINA")
        self.client.post(
            reverse("cocina:actualizar_estado", args=[orden.pk]), {"accion": "iniciar", "tiempo_estimado": "20"}
        )
        orden.refresh_from_db()
        self.assertEqual(orden.tiempo_estimado_min, 20)
        self.assertEqual(orden.listo_estimado_en, orden.preparacion_iniciada_en + timedelta(minutes=20))


    def test_cu_ped_15_enviar_total_del_pedido(self):
        orden = self.crear_orden(estado=Orden.LISTA, items=[(self.gaseosa, 2), (self.hamburguesa, 1)])
        self.entrar_como("MESERO")
        self.client.post(reverse("operativo:solicitar_cuenta", args=[orden.pk]))
        self.entrar_como("CAJERO")
        por_cobrar = list(self.client.get(reverse("caja:por_cobrar")).context["ordenes"])
        self.assertEqual(por_cobrar, [orden])
        self.assertEqual(por_cobrar[0].total, Decimal("30000"))
