from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from core.mixins import RoleRequiredMixin, rol_requerido, usuario_tiene_rol
from core.tenancy import RestauranteMixin, filtrar
from operativo.models import Orden, TransicionOrdenInvalida

from .forms import CobrarOrdenForm
from .models import Pago

ROLES_CAJA = ["ADMINISTRADOR", "CAJERO"]
ROLES_ENTREGA = ["ADMINISTRADOR", "CAJERO", "MESERO"]


def _orden_del_restaurante(request, pk):
    return get_object_or_404(filtrar(Orden.objects, request, "sucursal__restaurante"), pk=pk)


class PagoListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "orden__sucursal__restaurante"
    model = Pago
    roles_permitidos = ROLES_CAJA
    template_name = "caja/pagos_list.html"
    context_object_name = "pagos"
    queryset = Pago.objects.select_related("orden", "metodo_pago")


def cobrar_orden(request, pk):
    if not usuario_tiene_rol(request.user, ROLES_CAJA):
        return redirect("operativo:detalle_orden", pk=pk)
    orden = _orden_del_restaurante(request, pk)

    if request.method == "POST":
        form = CobrarOrdenForm(request.POST)
        if form.is_valid():
            if orden.pagos.exists():
                form.add_error(None, "Esta orden ya tiene un pago registrado.")
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            if not orden.cobrable:
                form.add_error(
                    None,
                    "Esta orden no se puede cobrar ahora: las de mesa se cobran cuando están LISTA y las "
                    "canceladas o entregadas no se cobran.",
                )
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            monto = form.cleaned_data["monto"]
            if monto < orden.total:
                form.add_error("monto", "El monto debe ser mayor o igual al total de la orden.")
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            estado_previo = orden.estado
            try:
                with transaction.atomic():
                    Pago.objects.create(
                        orden=orden,
                        metodo_pago=form.cleaned_data["metodo_pago"],
                        monto=monto,
                        referencia_transaccion=form.cleaned_data["referencia_transaccion"],
                    )
                    if estado_previo == Orden.LISTA:
                        orden.cambiar_estado(Orden.ENTREGADA)
                    elif estado_previo == Orden.POR_CONFIRMAR:
                        orden.cambiar_estado(Orden.PENDIENTE)
            except TransicionOrdenInvalida as error:
                form.add_error(None, error.messages[0])
                return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})
            if estado_previo == Orden.LISTA:
                return redirect("caja:ventas_list")
            messages.success(request, f"Orden #{orden.pk} pagada. Se entregará cuando cocina la tenga lista.")
            return redirect("caja:para_llevar")
    else:
        form = CobrarOrdenForm(initial={"monto": orden.total})

    return render(request, "caja/registrar_pago.html", {"orden": orden, "form": form})


class CuentasPorCobrarView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "sucursal__restaurante"
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


class ParaLlevarView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "sucursal__restaurante"
    model = Orden
    roles_permitidos = ROLES_CAJA
    template_name = "caja/para_llevar.html"
    context_object_name = "por_confirmar"
    queryset = (
        Orden.objects.filter(estado=Orden.POR_CONFIRMAR)
        .select_related("cliente", "sucursal")
        .prefetch_related("detalles__producto", "pagos")
        .order_by("creado_en")
    )

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        sin_mesa = filtrar(Orden.objects, self.request, "sucursal__restaurante").filter(mesa__isnull=True)
        contexto["en_cocina"] = (
            sin_mesa.filter(estado__in=[Orden.PENDIENTE, Orden.EN_PREPARACION])
            .select_related("cliente").prefetch_related("detalles", "pagos").order_by("creado_en")
        )
        contexto["listas"] = (
            sin_mesa.filter(estado=Orden.LISTA)
            .select_related("cliente").prefetch_related("detalles", "pagos").order_by("actualizado_en")
        )
        return contexto


@require_POST
@rol_requerido(*ROLES_CAJA)
def aceptar_orden(request, pk):
    orden = _orden_del_restaurante(request, pk)
    try:
        orden.cambiar_estado(Orden.PENDIENTE)
        messages.success(request, f"Orden #{orden.pk} aceptada: pasó a cocina. Se cobra al entregarla.")
    except TransicionOrdenInvalida as error:
        messages.error(request, error.messages[0])
    return redirect("caja:para_llevar")


@require_POST
@rol_requerido(*ROLES_CAJA)
def rechazar_orden(request, pk):
    orden = _orden_del_restaurante(request, pk)
    if orden.estado != Orden.POR_CONFIRMAR:
        messages.error(request, "Solo se pueden rechazar pedidos por confirmar.")
        return redirect("caja:para_llevar")
    orden.cambiar_estado(Orden.CANCELADA)
    messages.success(request, f"Orden #{orden.pk} rechazada. No llegó a cocina.")
    return redirect("caja:para_llevar")


@require_POST
@rol_requerido(*ROLES_ENTREGA)
def entregar_orden(request, pk):
    orden = _orden_del_restaurante(request, pk)
    destino = request.POST.get("volver") or "caja:para_llevar"
    if destino not in ("caja:para_llevar", "operativo:detalle_orden"):
        destino = "caja:para_llevar"
    if orden.estado != Orden.LISTA:
        messages.error(request, "Solo se entregan órdenes que cocina marcó como listas.")
    elif not orden.pagada:
        messages.error(request, f"La orden #{orden.pk} no está pagada: cóbrala antes de entregarla.")
        if usuario_tiene_rol(request.user, ROLES_CAJA):
            return redirect("caja:cobrar_orden", pk=orden.pk)
    else:
        orden.cambiar_estado(Orden.ENTREGADA)
        messages.success(request, f"Orden #{orden.pk} entregada.")
    if destino == "operativo:detalle_orden":
        return redirect(destino, pk=orden.pk)
    return redirect(destino)


class VentaListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "sucursal__restaurante"
    model = Orden
    roles_permitidos = ROLES_CAJA
    template_name = "caja/ventas_list.html"
    context_object_name = "ventas"
    queryset = (
        Orden.objects.filter(pagos__isnull=False)
        .distinct()
        .select_related("mesa", "cliente")
        .prefetch_related("pagos")
    )
