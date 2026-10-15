from django.urls import path

from .views import AsistenteView

app_name = "asistente_cocina"

urlpatterns = [
    path("", AsistenteView.as_view(), name="asistente"),
]
