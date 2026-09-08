from django.urls import path

from . import views

app_name = "caja"

urlpatterns = [
    path("pagos/", views.PagoListView.as_view(), name="pagos_list"),
    path("ordenes/<int:pk>/cobrar/", views.cobrar_orden, name="cobrar_orden"),
    path("ventas/", views.VentaListView.as_view(), name="ventas_list"),
]
