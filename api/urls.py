from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from . import views, views_cuenta, views_domicilio, views_operacion, views_publico

app_name = "api"

router = SimpleRouter()
router.register("inventario/items", views.ItemInventarioViewSet, basename="items-inventario")
router.register("ordenes", views_operacion.OrdenViewSet, basename="ordenes")
router.register("reservas", views_operacion.ReservaViewSet, basename="reservas")
router.register("cocina/ordenes", views_operacion.CocinaViewSet, basename="cocina")
router.register("cliente/direcciones", views_domicilio.DireccionViewSet, basename="direcciones")
router.register("cliente/domicilios", views_domicilio.DomicilioClienteViewSet, basename="domicilios-cliente")
router.register("domiciliario", views_domicilio.DomiciliarioViewSet, basename="domiciliario")

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
    path("publico/sucursales/", views_publico.SucursalPublicaListView.as_view(), name="sucursales_publicas"),
    path("publico/sucursales/<int:pk>/menu/", views_publico.MenuSucursalView.as_view(), name="menu_sucursal"),
    path("publico/pedidos/", views_publico.PedidoPublicoCrearView.as_view(), name="pedido_publico"),
    path("publico/pedidos/<str:codigo>/", views_publico.PedidoPublicoDetalleView.as_view(), name="pedido_publico_detalle"),
    path("menu/", views.MenuView.as_view(), name="menu"),
    path("schema/", SpectacularAPIView.as_view(), name="esquema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:esquema"), name="docs"),
] + router.urls
