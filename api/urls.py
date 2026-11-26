from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from . import views, views_caja, views_cliente_extra, views_cuenta, views_gestion, views_domicilio, views_operacion, views_publico

app_name = "api"

router = SimpleRouter()
router.register("inventario/items", views.ItemInventarioViewSet, basename="items-inventario")
router.register("ordenes", views_operacion.OrdenViewSet, basename="ordenes")
router.register("reservas", views_operacion.ReservaViewSet, basename="reservas")
router.register("cocina/ordenes", views_operacion.CocinaViewSet, basename="cocina")
router.register("cliente/direcciones", views_domicilio.DireccionViewSet, basename="direcciones")
router.register("cliente/domicilios", views_domicilio.DomicilioClienteViewSet, basename="domicilios-cliente")
router.register("domiciliario", views_domicilio.DomiciliarioViewSet, basename="domiciliario")
router.register("gestion/items", views_gestion.ItemGestionViewSet, basename="g-items")
router.register("gestion/proveedores", views_gestion.ProveedorGestionViewSet, basename="g-proveedores")
router.register("gestion/recetas", views_gestion.RecetaGestionViewSet, basename="g-recetas")
router.register("gestion/categorias", views_gestion.CategoriaGestionViewSet, basename="g-categorias")
router.register("gestion/productos", views_gestion.ProductoGestionViewSet, basename="g-productos")
router.register("gestion/mesas", views_gestion.MesaGestionViewSet, basename="g-mesas")
router.register("gestion/sucursales", views_gestion.SucursalGestionViewSet, basename="g-sucursales")
router.register("gestion/restaurantes", views_gestion.RestauranteGestionViewSet, basename="g-restaurantes")
router.register("gestion/usuarios", views_gestion.UsuarioGestionViewSet, basename="g-usuarios")
router.register("gestion/movimientos", views_gestion.MovimientoGestionViewSet, basename="g-movimientos")
router.register("gestion/compras", views_gestion.CompraGestionViewSet, basename="g-compras")
router.register("gestion/opiniones", views_gestion.OpinionGestionViewSet, basename="g-opiniones")

urlpatterns = [
    path("auth/token/", views.TokenView.as_view(), name="token"),
    path("auth/registro/cliente/", views_domicilio.RegistroClienteView.as_view(), name="registro_cliente"),
    path("cliente/perfil/", views_domicilio.PerfilClienteView.as_view(), name="perfil_cliente"),
    path("publico/mesas/<int:pk>/pedido/", views_domicilio.PedidoMesaView.as_view(), name="pedido_mesa"),
    path("auth/login/", views_cuenta.LoginView.as_view(), name="login"),
    path("auth/registro/admin/", views_cuenta.RegistroAdministradorView.as_view(), name="registro_admin"),
    path("auth/registro/empleado/", views_cuenta.RegistroEmpleadoView.as_view(), name="registro_empleado"),
    path("auth/verificar/", views_cuenta.VerificarView.as_view(), name="verificar"),
    path("auth/reenviar/", views_cuenta.ReenviarVerificacionView.as_view(), name="reenviar"),
    path("auth/recuperar/", views_cuenta.RecuperarView.as_view(), name="recuperar"),
    path("auth/recuperar/confirmar/", views_cuenta.RecuperarConfirmarView.as_view(), name="recuperar_confirmar"),
    path("auth/logout/", views_cuenta.LogoutView.as_view(), name="logout"),
    path("auth/yo/", views_cuenta.PerfilView.as_view(), name="yo"),
    path("mesas/", views_operacion.MesaListView.as_view(), name="mesas"),
    path("productos/", views_operacion.ProductoListView.as_view(), name="productos"),
    path("caja/por-cobrar/", views_operacion.PorCobrarView.as_view(), name="por_cobrar"),
    path("caja/para-llevar/", views_operacion.ParaLlevarView.as_view(), name="para_llevar"),
    path("caja/metodos/", views_caja.MetodosPagoView.as_view(), name="caja_metodos"),
    path("gestion/dashboard/", views_gestion.DashboardView.as_view(), name="g_dashboard"),
    path("gestion/opciones/", views_gestion.OpcionesView.as_view(), name="g_opciones"),
    path("gestion/reportes/pdf/", views_gestion.ReportePdfView.as_view(), name="g_reporte_pdf"),
    path("publico/sucursales/<int:pk>/reservas/", views_cliente_extra.ReservarView.as_view(), name="reservar"),
    path("publico/reservas/<str:codigo>/", views_cliente_extra.ReservaPublicaView.as_view(), name="reserva_publica"),
    path("publico/opiniones/", views_cliente_extra.OpinarView.as_view(), name="opinar"),
    path("caja/ordenes/<int:pk>/cuenta/", views_caja.CuentaView.as_view(), name="caja_cuenta"),
    path("caja/ordenes/<int:pk>/cobrar/", views_caja.CobrarView.as_view(), name="caja_cobrar"),
    path("caja/ordenes/<int:pk>/qr/", views_caja.QrCobroView.as_view(), name="caja_qr"),
    path("caja/ordenes/<int:pk>/aceptar/", views_caja.AceptarParaLlevarView.as_view(), name="caja_aceptar"),
    path("caja/ordenes/<int:pk>/rechazar/", views_caja.RechazarParaLlevarView.as_view(), name="caja_rechazar"),
    path("caja/ventas/", views_caja.VentasView.as_view(), name="caja_ventas"),
    path("caja/facturas/", views_caja.FacturasView.as_view(), name="caja_facturas"),
    path("caja/facturas/<int:pk>/", views_caja.FacturaDetalleView.as_view(), name="caja_factura"),
    path("publico/sucursales/", views_publico.SucursalPublicaListView.as_view(), name="sucursales_publicas"),
    path("publico/sucursales/<int:pk>/menu/", views_publico.MenuSucursalView.as_view(), name="menu_sucursal"),
    path("publico/pedidos/", views_publico.PedidoPublicoCrearView.as_view(), name="pedido_publico"),
    path("publico/pedidos/<str:codigo>/", views_publico.PedidoPublicoDetalleView.as_view(), name="pedido_publico_detalle"),
    path("publico/pedidos/<str:codigo>/pago/", views_publico.PagoPedidoPublicoView.as_view(), name="pedido_publico_pago"),
    path("menu/", views.MenuView.as_view(), name="menu"),
    path("schema/", SpectacularAPIView.as_view(), name="esquema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:esquema"), name="docs"),
] + router.urls
