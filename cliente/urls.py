from django.urls import path

from . import views

app_name = "cliente"

urlpatterns = [
    path("mesa/<int:mesa_id>/", views.mesa, name="mesa"),
    path("menu/", views.menu, name="menu"),
    path("pedido/", views.autopedido, name="autopedido"),
    path("pedido/<int:pk>/", views.pedido, name="pedido"),
    path("mis-pedidos/", views.mis_pedidos, name="mis_pedidos"),
    path("opinion/", views.retroalimentacion, name="retroalimentacion"),
    path("retroalimentacion/", views.RetroalimentacionListView.as_view(), name="retroalimentacion_list"),
    path("retroalimentacion/<int:pk>/revisar/", views.retroalimentacion_revisar, name="retroalimentacion_revisar"),
]
