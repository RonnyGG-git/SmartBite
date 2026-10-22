from collections import OrderedDict
from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from core.mixins import RoleRequiredMixin, rol_requerido
from core.tenancy import RestauranteMixin, filtrar
from operativo.models import Orden

ROLES_COCINA = ["ADMINISTRADOR", "JEFE_COCINA"]
TIEMPOS_ESTIMADOS = [5, 10, 15, 20, 30, 45, 60]


def insumos_faltantes(orden):
    requerido = OrderedDict()
    for detalle in orden.detalles.all():
        for ing in detalle.producto.ingredientes.all():
            if not ing.activo:
                continue
            item = ing.item_inventario
            requerido[item] = requerido.get(item, Decimal("0")) + ing.cantidad_requerida * detalle.cantidad
    return [item for item, cantidad in requerido.items() if item.stock_actual < cantidad]


class CocinaListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "mesa__sucursal__restaurante"
    roles_permitidos = ROLES_COCINA
    template_name = "cocina/cocina.html"
    context_object_name = "ordenes"
    queryset = (
        Orden.objects.filter(estado__in=[Orden.PENDIENTE, Orden.EN_PREPARACION])
        .select_related("mesa")
        .prefetch_related("detalles__producto__ingredientes__item_inventario")
    )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        for orden in contexto["ordenes"]:
            orden.faltantes = insumos_faltantes(orden)
        contexto["tiempos_estimados"] = TIEMPOS_ESTIMADOS
        return contexto


@require_POST
@rol_requerido(*ROLES_COCINA)
def actualizar_estado(request, pk):
    orden = get_object_or_404(filtrar(Orden.objects, request, "mesa__sucursal__restaurante"), pk=pk)
    accion = request.POST.get("accion")

    if accion == "iniciar" and orden.estado == Orden.PENDIENTE:
        try:
            minutos = int(request.POST.get("tiempo_estimado", ""))
        except ValueError:
            minutos = 0
        if not 1 <= minutos <= 240:
            messages.error(request, "Indica un tiempo estimado de preparación válido.")
            return redirect("cocina:cocina")
        orden.cambiar_estado(
            Orden.EN_PREPARACION,
            tiempo_estimado_min=minutos,
            preparacion_iniciada_en=timezone.now(),
        )
        messages.success(request, f"Orden #{orden.pk} en preparación ({minutos} min).")
    elif accion == "listo" and orden.estado == Orden.EN_PREPARACION:
        orden.cambiar_estado(Orden.LISTA)
        messages.success(request, f"Orden #{orden.pk} lista para servir en la mesa {orden.mesa.numero}.")
    else:
        messages.error(request, "Esa acción ya no aplica al estado actual de la orden.")
    return redirect("cocina:cocina")
