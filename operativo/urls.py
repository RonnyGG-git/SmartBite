from django.urls import path

from . import views

app_name = "operativo"

urlpatterns = [
    path("mesas/", views.MesaListView.as_view(), name="mesas_list"),
    path("mesas/nueva/", views.MesaCreateView.as_view(), name="mesa_crear"),
    path("mesas/<int:pk>/editar/", views.MesaUpdateView.as_view(), name="mesa_editar"),
    path("mesas/<int:pk>/eliminar/", views.MesaDeleteView.as_view(), name="mesa_eliminar"),
    path("mesas/qr/<int:mesa_id>/", views.generar_qr, name="generar_qr"),

    path("ordenes/nueva/", views.crear_orden, name="crear_orden"),
    path("ordenes/clientes/nuevo/", views.crear_cliente_rapido, name="crear_cliente_rapido"),
    path("ordenes/<int:pk>/", views.DetalleOrdenView.as_view(), name="detalle_orden"),
    path("ordenes/<int:pk>/productos/", views.agregar_producto, name="agregar_producto"),
    path("ordenes/<int:pk>/estado/", views.cambiar_estado_orden, name="cambiar_estado_orden"),
]
