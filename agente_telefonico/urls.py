from django.urls import path

from . import views, views_twilio

app_name = "agente_telefonico"

urlpatterns = [
    path("twilio/voz/", views_twilio.voz_entrante, name="twilio_voz"),
    path("twilio/voz/turno/", views_twilio.voz_turno, name="twilio_voz_turno"),
    path("twilio/voz/estado/", views_twilio.voz_estado, name="twilio_voz_estado"),
    path("twilio/whatsapp/", views_twilio.whatsapp, name="twilio_whatsapp"),
    path("simulador/", views.SimuladorView.as_view(), name="simulador"),
    path("simulador/llamadas/", views.demo_iniciar, name="demo_iniciar"),
    path("simulador/llamadas/<int:pk>/turno/", views.demo_turno, name="demo_turno"),
    path("simulador/llamadas/<int:pk>/colgar/", views.demo_colgar, name="demo_colgar"),
]
