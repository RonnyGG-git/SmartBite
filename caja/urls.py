from django.urls import path

from . import views

app_name = "caja"

urlpatterns = [
    path("por-cobrar/", views.CuentasPorCobrarView.as_view(), name="por_cobrar"),
    path("pagos/", views.PagoListView.as_view(), name="pagos_list"),
    path("ordenes/<int:pk>/cobrar/", views.cobrar_orden, name="cobrar_orden"),
    path("ventas/", views.VentaListView.as_view(), name="ventas_list"),
    path("para-llevar/", views.ParaLlevarView.as_view(), name="para_llevar"),
    path("ordenes/<int:pk>/aceptar/", views.aceptar_orden, name="aceptar_orden"),
    path("ordenes/<int:pk>/rechazar/", views.rechazar_orden, name="rechazar_orden"),
    path("ordenes/<int:pk>/entregar/", views.entregar_orden, name="entregar_orden"),
]
