from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from core.mixins import RoleRequiredMixin, usuario_tiene_rol
from operativo.models import Mesa, Orden

from .forms import CobrarOrdenForm
from .models import Pago

ROLES_CAJA = ["ADMINISTRADOR", "CAJERO"]


class PagoListView(RoleRequiredMixin, ListView):
    model = Pago
    roles_permitidos = ROLES_CAJA
    template_name = "caja/pagos_list.html"
    context_object_name = "pagos"
    queryset = Pago.objects.select_related("orden", "metodo_pago")


def cobrar_orden(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    if not usuario_tiene_rol(request.user, ROLES_CAJA):
        return redirect("operativo:detalle_orden", pk=pk)

    if request.method == "POST":
        form = CobrarOrdenForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                Pago.objects.create(
                    orden=orden,
                    metodo_pago=form.cleaned_data["metodo_pago"],
                    monto=form.cleaned_data["monto"],
                    referencia_transaccion=form.cleaned_data["referencia_transaccion"],
                )
                orden.estado = Orden.ENTREGADA
                orden.save(update_fields=["estado"])
                orden.mesa.estado = Mesa.DISPONIBLE
                orden.mesa.save(update_fields=["estado"])
            # El cajero no tiene acceso a Mesas; vuelve a su historial de ventas
            return redirect("caja:ventas_list")
    else:
        form = CobrarOrdenForm(initial={"monto": orden.total})

    return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})


class CuentasPorCobrarView(RoleRequiredMixin, ListView):
    """CU-PAG-16 Confirmar pedido: órdenes cuya cuenta pidió el mesero (CU-PED-14)."""

    model = Orden
    roles_permitidos = ROLES_CAJA
    template_name = "caja/por_cobrar.html"
    context_object_name = "ordenes"
    queryset = (
        Orden.objects.filter(cuenta_solicitada_en__isnull=False)
        .exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA])
        .select_related("mesa", "cliente")
        .prefetch_related("detalles")
        .order_by("cuenta_solicitada_en")
    )


class VentaListView(RoleRequiredMixin, ListView):
    model = Orden
    roles_permitidos = ROLES_CAJA
    template_name = "caja/ventas_list.html"
    context_object_name = "ventas"
    queryset = Orden.objects.filter(estado=Orden.ENTREGADA).select_related("mesa", "cliente").prefetch_related("pagos")
