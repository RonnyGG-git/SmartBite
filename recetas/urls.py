from django.urls import path

from . import views

app_name = "recetas"

urlpatterns = [
    path("", views.RecetaListView.as_view(), name="recetas_list"),
    path("nueva/", views.RecetaCreateView.as_view(), name="receta_crear"),
    path("<int:pk>/editar/", views.RecetaUpdateView.as_view(), name="receta_editar"),
    path("<int:pk>/eliminar/", views.RecetaDeleteView.as_view(), name="receta_eliminar"),
]
