from django.views.generic import ListView

from core.mixins import RoleRequiredMixin
from operativo.models import Orden

ROLES_COCINA = ["ADMINISTRADOR", "JEFE_COCINA"]


class CocinaListView(RoleRequiredMixin, ListView):
    roles_permitidos = ROLES_COCINA
    template_name = "cocina/cocina.html"
    context_object_name = "ordenes"
    queryset = (
        Orden.objects.filter(estado__in=[Orden.PENDIENTE, Orden.EN_PREPARACION])
        .select_related("mesa")
        .prefetch_related("detalles__producto")
    )
