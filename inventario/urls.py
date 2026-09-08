from django.urls import path

from . import views

app_name = "inventario"

urlpatterns = [
    path("", views.ItemInventarioListView.as_view(), name="inventario_list"),
    path("nuevo/", views.ItemInventarioCreateView.as_view(), name="item_crear"),
    path("<int:pk>/editar/", views.ItemInventarioUpdateView.as_view(), name="item_editar"),
    path("<int:pk>/ajustar/", views.item_ajustar_stock, name="item_ajustar"),

    path("movimientos/", views.MovimientoInventarioListView.as_view(), name="movimientos_list"),

    path("proveedores/", views.ProveedorListView.as_view(), name="proveedores_list"),
    path("proveedores/nuevo/", views.ProveedorCreateView.as_view(), name="proveedor_crear"),
    path("proveedores/<int:pk>/editar/", views.ProveedorUpdateView.as_view(), name="proveedor_editar"),
    path("proveedores/<int:pk>/eliminar/", views.ProveedorDeleteView.as_view(), name="proveedor_eliminar"),

    path("compras/", views.CompraListView.as_view(), name="compras_list"),
    path("compras/nueva/", views.compra_crear, name="compra_crear"),
    path("compras/<int:pk>/", views.CompraDetailView.as_view(), name="compra_detalle"),
    path("compras/<int:pk>/recibir/", views.compra_recibir, name="compra_recibir"),
    path("compras/<int:pk>/anular/", views.compra_anular, name="compra_anular"),
]
