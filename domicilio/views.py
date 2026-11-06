from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, ListView

from core.mixins import RoleRequiredMixin
from core.tenancy import filtrar

from .models import Domicilio

ROLES_DOMICILIO = ["ADMINISTRADOR", "DOMICILIARIO", "CAJERO"]
RUTA = "orden__sucursal__restaurante"


def domicilios_del_restaurante(request):
    return filtrar(
        Domicilio.objects.select_related("orden__sucursal", "cliente", "domiciliario"),
        request,
        RUTA,
    )


class PanelView(RoleRequiredMixin, ListView):
    roles_permitidos = ROLES_DOMICILIO
    template_name = "domicilio/panel.html"
    context_object_name = "activos"

    def get_queryset(self):
        return domicilios_del_restaurante(self.request).exclude(estado__in=Domicilio.FINALES).order_by("creado_en")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["recientes"] = domicilios_del_restaurante(self.request).filter(estado__in=Domicilio.FINALES)[:15]
        return contexto


class SeguimientoView(RoleRequiredMixin, DetailView):
    roles_permitidos = ROLES_DOMICILIO
    template_name = "domicilio/seguimiento.html"
    context_object_name = "domicilio"

    def get_object(self, queryset=None):
        return get_object_or_404(domicilios_del_restaurante(self.request), pk=self.kwargs["pk"])
