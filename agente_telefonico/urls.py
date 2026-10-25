from django.urls import path

from . import views

app_name = "agente_telefonico"

urlpatterns = [
    path("simulador/", views.SimuladorView.as_view(), name="simulador"),
    path("simulador/llamadas/", views.demo_iniciar, name="demo_iniciar"),
    path("simulador/llamadas/<int:pk>/turno/", views.demo_turno, name="demo_turno"),
    path("simulador/llamadas/<int:pk>/colgar/", views.demo_colgar, name="demo_colgar"),
]
