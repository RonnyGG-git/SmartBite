from django.urls import path

from . import views, vistas_qr

app_name = "caja"

urlpatterns = [
    path("", views.ParaLlevarView.as_view(), name="para_llevar"),
    path("por-cobrar/", views.CuentasPorCobrarView.as_view(), name="por_cobrar"),
    path("pagos/", views.PagoListView.as_view(), name="pagos_list"),
    path("pagos/retorno/", views.retorno_pago, name="retorno_pago"),
    path("ordenes/<int:pk>/cobrar/", views.cobrar_orden, name="cobrar_orden"),
    path("ordenes/<int:pk>/aceptar/", views.aceptar_orden, name="aceptar_orden"),
    path("ordenes/<int:pk>/rechazar/", views.rechazar_orden, name="rechazar_orden"),
    path("ordenes/<int:pk>/entregar/", views.entregar_orden, name="entregar_orden"),
    path("ventas/", views.VentaListView.as_view(), name="ventas_list"),
    path("auditoria/", views.auditoria_list, name="auditoria_list"),
    path("webhooks/<str:proveedor>/", views.webhook, name="webhook"),
    path("pasarela-simulada/<str:referencia>/", views.pasarela_simulada, name="pasarela_simulada"),

    # Cobro por QR (celular del cliente)
    path("ordenes/<int:pk>/qr/", vistas_qr.qr_cobro, name="qr_cobro"),
    path("ordenes/<int:pk>/estado/", vistas_qr.estado_orden, name="estado_orden"),
    path("pagar/<str:token>/", vistas_qr.pagar_cliente, name="pagar_cliente"),
    path("pagar/<str:token>/listo/", vistas_qr.pago_listo, name="pago_listo"),
    path("pagar/<str:token>/estado/", vistas_qr.estado_pago, name="estado_pago"),
    path("pagar/<str:token>/factura/", vistas_qr.factura_publica, name="factura_publica"),

    # Comprobantes
    path("facturas/", vistas_qr.FacturaListView.as_view(), name="facturas_list"),
    path("facturas/<int:pk>/", vistas_qr.factura_detalle, name="factura_detalle"),
]
