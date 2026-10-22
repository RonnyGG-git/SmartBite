from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from core.mixins import RoleRequiredMixin, usuario_tiene_rol
from core.tenancy import RestauranteMixin, filtrar
from operativo.models import Orden, TransicionOrdenInvalida

from .forms import CobrarOrdenForm
from .models import Pago

ROLES_CAJA = ["ADMINISTRADOR", "CAJERO"]


class PagoListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "orden__mesa__sucursal__restaurante"
    model = Pago
    roles_permitidos = ROLES_CAJA
    template_name = "caja/pagos_list.html"
    context_object_name = "pagos"
    queryset = Pago.objects.select_related("orden", "metodo_pago")


def cobrar_orden(request, pk):
    if not usuario_tiene_rol(request.user, ROLES_CAJA):
        return redirect("operativo:detalle_orden", pk=pk)
    orden = get_object_or_404(filtrar(Orden.objects, request, "mesa__sucursal__restaurante"), pk=pk)

    if request.method == "POST":
        form = CobrarOrdenForm(request.POST)
        if form.is_valid():
            if orden.estado != Orden.LISTA:
                form.add_error(None, "Solo se pueden cobrar ordenes en estado LISTA.")
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            if orden.pagos.exists():
                form.add_error(None, "Esta orden ya tiene un pago registrado.")
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            monto = form.cleaned_data["monto"]
            if monto < orden.total:
                form.add_error("monto", "El monto debe ser mayor o igual al total de la orden.")
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            try:
                with transaction.atomic():
                    Pago.objects.create(
                        orden=orden,
                        metodo_pago=form.cleaned_data["metodo_pago"],
                        monto=monto,
                        referencia_transaccion=form.cleaned_data["referencia_transaccion"],
                    )
                    orden.cambiar_estado(Orden.ENTREGADA)
            except TransicionOrdenInvalida as error:
                form.add_error(None, error.messages[0])
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            return redirect("caja:ventas_list")
    else:
        form = CobrarOrdenForm(initial={"monto": orden.total})

    return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})


class CuentasPorCobrarView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "mesa__sucursal__restaurante"
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


class VentaListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "mesa__sucursal__restaurante"
    model = Orden
    roles_permitidos = ROLES_CAJA
    template_name = "caja/ventas_list.html"
    context_object_name = "ventas"
    queryset = Orden.objects.filter(estado=Orden.ENTREGADA).select_related("mesa", "cliente").prefetch_related("pagos")
