from django.urls import path
<<<<<<< Updated upstream
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter
=======
>>>>>>> Stashed changes

from . import views

app_name = "api"

<<<<<<< Updated upstream
router = SimpleRouter()
router.register("inventario/items", views.ItemInventarioViewSet, basename="items-inventario")

urlpatterns = [
    path("auth/token/", views.TokenView.as_view(), name="token"),
    path("menu/", views.MenuView.as_view(), name="menu"),
    path("schema/", SpectacularAPIView.as_view(), name="esquema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:esquema"), name="docs"),
] + router.urls
=======
urlpatterns = [
    path("prueba-error/", views.EndpointDePruebaView.as_view(), name="prueba_error"),
    path("prueba-detalle/", views.EndpointDePruebaConDetalleView.as_view(), name="prueba_detalle"),
    path(
        "prueba-inesperado/",
        views.EndpointDeErrorInesperadoView.as_view(),
        name="prueba_inesperado",
    ),
    path("ordenes/<int:pk>/transicion/", views.TransicionOrdenView.as_view(), name="transicion_orden"),
]
>>>>>>> Stashed changes
