import base64
from io import BytesIO

import qrcode
from django.db import transaction
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from catalogo.models import Producto
from core.mixins import RoleRequiredMixin, rol_requerido, usuario_tiene_rol

from .forms import AgregarProductoForm, CambiarEstadoOrdenForm, ClienteRapidoForm, CrearOrdenForm, MesaForm
from .models import Cliente, DetalleOrden, Mesa, Orden

ROLES_ADMIN = ["ADMINISTRADOR"]
ROLES_MESERO = ["ADMINISTRADOR", "MESERO"]
ROLES_ORDEN = ["ADMINISTRADOR", "MESERO", "CAJERO"]
ROLES_CAJA = ["ADMINISTRADOR", "CAJERO"]


class MesaListView(RoleRequiredMixin, ListView):
    model = Mesa
    roles_permitidos = ROLES_MESERO
    template_name = "operativo/mesas_list.html"
    context_object_name = "mesas"
    queryset = Mesa.objects.select_related("sucursal").prefetch_related("ordenes")


class MesaCreateView(RoleRequiredMixin, CreateView):
    model = Mesa
    form_class = MesaForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Mesa"}
    success_url = reverse_lazy("operativo:mesas_list")


class MesaUpdateView(RoleRequiredMixin, UpdateView):
    model = Mesa
    form_class = MesaForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Mesa"}
    success_url = reverse_lazy("operativo:mesas_list")


class MesaDeleteView(RoleRequiredMixin, DeleteView):
    model = Mesa
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("operativo:mesas_list")


def crear_orden(request):
    if not usuario_tiene_rol(request.user, ROLES_MESERO):
        return redirect("operativo:mesas_list")

    mesa_id = request.GET.get("mesaId")
    cliente_form = ClienteRapidoForm()

    if request.method == "POST":
        form = CrearOrdenForm(request.POST)
        if form.is_valid():
            # RF-010: transaccion atomica con bloqueo selectivo de la fila de
            # la mesa y verificacion de orden activa antes de crear.
            with transaction.atomic():
                mesa_bloqueada = Mesa.objects.select_for_update().get(
                    pk=form.cleaned_data["mesa"].pk
                )
                if mesa_bloqueada.orden_activa is not None:
                    form.add_error(None, "Esta mesa ya tiene una orden activa.")
                else:
                    orden = form.save(commit=False)
                    orden.mesa = mesa_bloqueada
                    orden.save()
                    mesa_bloqueada.estado = Mesa.OCUPADA
                    mesa_bloqueada.save(update_fields=["estado"])
                    return redirect("operativo:detalle_orden", pk=orden.pk)
    else:
        initial = {"mesa": mesa_id} if mesa_id else {}
        form = CrearOrdenForm(initial=initial)

    return render(
        request,
        "operativo/crear_orden.html",
        {"form": form, "cliente_form": cliente_form},
    )


@require_POST
@rol_requerido(*ROLES_MESERO)
def crear_cliente_rapido(request):
    form = ClienteRapidoForm(request.POST)
    if form.is_valid():
        form.save()
    return redirect(request.META.get("HTTP_REFERER", reverse("operativo:crear_orden")))


class DetalleOrdenView(RoleRequiredMixin, DetailView):
    model = Orden
    roles_permitidos = ROLES_ORDEN
    template_name = "operativo/detalle_orden.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        productos_qs = Producto.objects.filter(disponible=True, sucursal=self.object.mesa.sucursal)
        contexto["agregar_form"] = AgregarProductoForm(productos_qs=productos_qs)
        # Qué acciones ve cada rol (las vistas POST vuelven a validarlo)
        contexto["puede_operar"] = usuario_tiene_rol(self.request.user, ROLES_MESERO)
        contexto["puede_cobrar"] = usuario_tiene_rol(self.request.user, ROLES_CAJA)
        return contexto


@rol_requerido(*ROLES_MESERO)
@require_POST
@rol_requerido(*ROLES_MESERO)
def agregar_producto(request, pk):
    """CU-PED-06 Modificar pedido: solo antes de que cocina empiece a prepararlo."""
    orden = get_object_or_404(Orden, pk=pk)
    if orden.estado != Orden.PENDIENTE:
        messages.error(request, "La orden ya está en cocina; no se pueden agregar productos.")
        return redirect("operativo:detalle_orden", pk=pk)
    productos_qs = Producto.objects.filter(disponible=True, sucursal=orden.mesa.sucursal)
    form = AgregarProductoForm(request.POST, productos_qs=productos_qs)
    if form.is_valid():
        producto = form.cleaned_data["producto"]
        DetalleOrden.objects.create(
            orden=orden,
            producto=producto,
            cantidad=form.cleaned_data["cantidad"],
            precio_unitario=producto.precio,
        )
    return redirect("operativo:detalle_orden", pk=pk)


# Transiciones que el Mesero puede hacer desde el detalle de la orden. Las de
# preparación (PENDIENTE -> EN_PREPARACION -> LISTA) son del Chef, en cocina, y
# el cierre (ENTREGADA) lo hace caja al cobrar, para que no haya ventas sin pago.
TRANSICIONES_MESERO = {
    Orden.CANCELADA: {Orden.PENDIENTE},  # CU-PED-07: antes de que se prepare
}


@require_POST
@rol_requerido(*ROLES_MESERO)
def solicitar_cuenta(request, pk):
    """CU-PED-14 Solicitar cuenta (incluye CU-PED-15 Enviar total del pedido):
    la orden pasa a la lista "Por cobrar" de caja."""
    orden = get_object_or_404(Orden, pk=pk)
    if orden.estado != Orden.LISTA:
        messages.error(request, "Solo se puede pedir la cuenta de una orden lista y servida.")
    elif orden.cuenta_solicitada_en is None:
        orden.cuenta_solicitada_en = timezone.now()
        orden.save(update_fields=["cuenta_solicitada_en", "actualizado_en"])
        messages.success(request, f"Cuenta de la mesa {orden.mesa.numero} enviada a caja.")
    return redirect("operativo:detalle_orden", pk=pk)


@rol_requerido(*ROLES_MESERO)
@require_POST
@rol_requerido(*ROLES_MESERO)
def cambiar_estado_orden(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    form = CambiarEstadoOrdenForm(request.POST)
    if form.is_valid():
        nuevo = form.cleaned_data["estado"]
        if orden.estado not in TRANSICIONES_MESERO.get(nuevo, set()):
            messages.error(request, "Ese cambio de estado no está permitido para esta orden.")
            return redirect("operativo:detalle_orden", pk=pk)
        orden.estado = nuevo
        orden.save(update_fields=["estado"])
        if nuevo in (Orden.ENTREGADA, Orden.CANCELADA):
            # CU-PED-21: al cancelar (o cerrar) el pedido la mesa queda libre
            orden.mesa.estado = Mesa.DISPONIBLE
            orden.mesa.save(update_fields=["estado"])
    return redirect("operativo:detalle_orden", pk=pk)


@rol_requerido(*ROLES_MESERO)
def generar_qr(request, mesa_id):
    mesa = get_object_or_404(Mesa, pk=mesa_id)
    url_menu = request.build_absolute_uri(reverse("cliente:mesa", args=[mesa.id]))

    imagen = qrcode.make(url_menu)
    buffer = BytesIO()
    imagen.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    return render(
        request,
        "operativo/generar_qr.html",
        {"mesa": mesa, "url_menu": url_menu, "qr_base64": qr_base64},
    )
