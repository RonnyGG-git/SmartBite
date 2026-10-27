from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import SimpleRouter

from . import views

app_name = "api"

router = SimpleRouter()
router.register("inventario/items", views.ItemInventarioViewSet, basename="items-inventario")

urlpatterns = [
    path("auth/token/", views.TokenView.as_view(), name="token"),
    path("menu/", views.MenuView.as_view(), name="menu"),
    path("schema/", SpectacularAPIView.as_view(), name="esquema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:esquema"), name="docs"),
] + router.urls
