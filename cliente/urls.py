from django.urls import path

from . import views, views_cuenta

app_name = "cliente"

urlpatterns = [
    path("", views.restaurantes, name="restaurantes"),
    path("inicio/", views_cuenta.inicio, name="inicio"),
    path("escanear/", views_cuenta.escanear, name="escanear"),
    path("cuenta/", views_cuenta.cuenta, name="cuenta"),
    path("cuenta/direcciones/nueva/", views_cuenta.direccion, name="direccion_crear"),
    path("cuenta/direcciones/<int:pk>/", views_cuenta.direccion, name="direccion_editar"),
    path("cuenta/direcciones/<int:pk>/eliminar/", views_cuenta.direccion_eliminar, name="direccion_eliminar"),
    path("domicilios/", views_cuenta.domicilios, name="domicilios"),
    path("domicilios/<int:pk>/", views_cuenta.domicilio_detalle, name="domicilio"),
    path("domicilios/<int:pk>/estado/", views_cuenta.domicilio_estado, name="domicilio_estado"),
    path("domicilios/<int:pk>/cancelar/", views_cuenta.domicilio_cancelar, name="domicilio_cancelar"),
    path("restaurante/<int:sucursal_id>/", views.sucursal, name="sucursal"),
    path("mesa/<int:mesa_id>/", views.mesa, name="mesa"),
    path("tipo/", views.tipo_consumo, name="tipo_consumo"),
    path("menu/", views.menu, name="menu"),
    path("carrito/", views.carrito, name="carrito"),
    path("compra/", views.compra, name="compra"),
    path("pedido/", views.autopedido, name="autopedido"),
    path("pedido/<int:pk>/", views.pedido, name="pedido"),
    path("mis-pedidos/", views.mis_pedidos, name="mis_pedidos"),
    path("reservar/", views.reservar, name="reservar"),
    path("reserva/<str:codigo>/", views.reserva, name="reserva"),
    path("reserva/<str:codigo>/cancelar/", views.cancelar_reserva, name="cancelar_reserva"),
    path("opinion/", views.retroalimentacion, name="retroalimentacion"),
    path("retroalimentacion/", views.RetroalimentacionListView.as_view(), name="retroalimentacion_list"),
    path("retroalimentacion/<int:pk>/revisar/", views.retroalimentacion_revisar, name="retroalimentacion_revisar"),
]
