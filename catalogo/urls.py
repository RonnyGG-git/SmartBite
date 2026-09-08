from django.urls import path

from . import views

app_name = "catalogo"

urlpatterns = [
    path("", views.ProductoListView.as_view(), name="productos_list"),
    path("nuevo/", views.ProductoCreateView.as_view(), name="producto_crear"),
    path("<int:pk>/editar/", views.ProductoUpdateView.as_view(), name="producto_editar"),
    path("<int:pk>/eliminar/", views.ProductoDeleteView.as_view(), name="producto_eliminar"),
    path("<int:pk>/disponibilidad/", views.producto_toggle_disponibilidad, name="producto_toggle_disponibilidad"),

    path("categorias/", views.CategoriaListView.as_view(), name="categorias_list"),
    path("categorias/nueva/", views.CategoriaCreateView.as_view(), name="categoria_crear"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria_editar"),
    path("categorias/<int:pk>/eliminar/", views.CategoriaDeleteView.as_view(), name="categoria_eliminar"),
]
