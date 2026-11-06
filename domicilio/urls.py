from django.urls import path

from . import views

app_name = "domicilio"

urlpatterns = [
    path("", views.PanelView.as_view(), name="panel"),
    path("<int:pk>/", views.SeguimientoView.as_view(), name="seguimiento"),
]
