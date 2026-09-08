from django.urls import path

from . import views

app_name = "restaurantes"

urlpatterns = [
    path("", views.RestauranteListView.as_view(), name="restaurantes_list"),
    path("nuevo/", views.RestauranteCreateView.as_view(), name="restaurante_crear"),
    path("<int:pk>/editar/", views.RestauranteUpdateView.as_view(), name="restaurante_editar"),
    path("<int:pk>/eliminar/", views.RestauranteDeleteView.as_view(), name="restaurante_eliminar"),

    path("sucursales/", views.SucursalListView.as_view(), name="sucursales_list"),
    path("sucursales/nueva/", views.SucursalCreateView.as_view(), name="sucursal_crear"),
    path("sucursales/<int:pk>/editar/", views.SucursalUpdateView.as_view(), name="sucursal_editar"),
    path("sucursales/<int:pk>/eliminar/", views.SucursalDeleteView.as_view(), name="sucursal_eliminar"),
]
