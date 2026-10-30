import base64
from io import BytesIO

import qrcode
from django.db import transaction
from django.db.models import ProtectedError
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from catalogo.models import Producto
from core.mixins import RoleRequiredMixin, rol_requerido, usuario_tiene_rol
from core.tenancy import RestauranteMixin, filtrar, limitar_opciones, restaurante_actual

from .forms import AgregarProductoForm, CambiarEstadoOrdenForm, ClienteRapidoForm, CrearOrdenForm, MesaForm
from .models import Cliente, DetalleOrden, Mesa, Orden, TransicionOrdenInvalida

ROLES_ADMIN = ["ADMINISTRADOR"]
ROLES_MESERO = ["ADMINISTRADOR", "MESERO"]
ROLES_ORDEN = ["ADMINISTRADOR", "MESERO", "CAJERO"]
ROLES_CAJA = ["ADMINISTRADOR", "CAJERO"]


class MesaListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "sucursal__restaurante"
    model = Mesa
    roles_permitidos = ROLES_MESERO
    template_name = "operativo/mesas_list.html"
    context_object_name = "mesas"
    queryset = Mesa.objects.select_related("sucursal").prefetch_related("ordenes")

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["pedidos_sin_mesa"] = (
            filtrar(Orden.objects, self.request, "sucursal__restaurante")
            .filter(mesa__isnull=True)
            .exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA])
            .select_related("cliente", "sucursal")
            .order_by("creado_en")
        )
        contexto["puede_gestionar"] = usuario_tiene_rol(self.request.user, ROLES_ADMIN)
        return contexto


class MesaCreateView(RestauranteMixin, RoleRequiredMixin, CreateView):
    ruta_restaurante = "sucursal__restaurante"
    model = Mesa
    form_class = MesaForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Nueva Mesa"}
    success_url = reverse_lazy("operativo:mesas_list")


class MesaUpdateView(RestauranteMixin, RoleRequiredMixin, UpdateView):
    ruta_restaurante = "sucursal__restaurante"
    model = Mesa
    form_class = MesaForm
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/generic_form.html"
    extra_context = {"titulo": "Editar Mesa"}
    success_url = reverse_lazy("operativo:mesas_list")


class MesaDeleteView(RestauranteMixin, RoleRequiredMixin, DeleteView):
    ruta_restaurante = "sucursal__restaurante"
    model = Mesa
    roles_permitidos = ROLES_ADMIN
    template_name = "includes/confirm_delete.html"
    success_url = reverse_lazy("operativo:mesas_list")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            messages.error(
                self.request,
                f"La mesa {self.object.numero} tiene órdenes registradas y no se puede eliminar. Desactívala en su lugar.",
            )
            return redirect("operativo:mesa_editar", pk=self.object.pk)


def crear_orden(request):
    if not usuario_tiene_rol(request.user, ROLES_MESERO):
        return redirect("operativo:mesas_list")

    mesa_id = request.GET.get("mesaId")
    cliente_form = ClienteRapidoForm()

    if request.method == "POST":
        form = limitar_opciones(CrearOrdenForm(request.POST), request)
        if form.is_valid():
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
        form = limitar_opciones(CrearOrdenForm(initial=initial), request)

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
        cliente = form.save(commit=False)
        cliente.restaurante = restaurante_actual(request)
        cliente.save()
    return redirect("operativo:crear_orden")


class DetalleOrdenView(RestauranteMixin, RoleRequiredMixin, DetailView):
    ruta_restaurante = "sucursal__restaurante"
    model = Orden
    roles_permitidos = ROLES_ORDEN
    template_name = "operativo/detalle_orden.html"
    context_object_name = "orden"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        productos_qs = Producto.objects.filter(disponible=True, sucursal=self.object.sucursal)
        contexto["agregar_form"] = AgregarProductoForm(productos_qs=productos_qs)
        contexto["puede_operar"] = usuario_tiene_rol(self.request.user, ROLES_MESERO)
        contexto["puede_cobrar"] = usuario_tiene_rol(self.request.user, ROLES_CAJA)
        if self.object.mesa_id is None and not self.object.es_final:
            contexto["mesas_libres"] = Mesa.objects.filter(
                sucursal=self.object.sucursal, activa=True, estado=Mesa.DISPONIBLE
            )
        return contexto


@require_POST
@rol_requerido(*ROLES_MESERO)
def asignar_mesa(request, pk):
    orden = get_object_or_404(filtrar(Orden.objects, request, "sucursal__restaurante"), pk=pk)
    if orden.mesa_id or orden.es_final:
        messages.error(request, "Esta orden ya tiene mesa o ya terminó.")
        return redirect("operativo:detalle_orden", pk=pk)
    with transaction.atomic():
        mesa = (
            Mesa.objects.select_for_update()
            .filter(pk=request.POST.get("mesa") or 0, sucursal=orden.sucursal_id, activa=True)
            .first()
        )
        if mesa is None or mesa.estado != Mesa.DISPONIBLE or mesa.orden_activa is not None:
            messages.error(request, "Esa mesa ya no está disponible.")
            return redirect("operativo:detalle_orden", pk=pk)
        Orden.objects.filter(pk=orden.pk, mesa__isnull=True).update(mesa=mesa)
        mesa.estado = Mesa.OCUPADA
        mesa.save(update_fields=["estado"])
    messages.success(request, f"Mesa {mesa.numero} asignada a la orden #{orden.pk}.")
    return redirect("operativo:detalle_orden", pk=pk)


@rol_requerido(*ROLES_MESERO)
@require_POST
@rol_requerido(*ROLES_MESERO)
def agregar_producto(request, pk):
    orden = get_object_or_404(filtrar(Orden.objects, request, "sucursal__restaurante"), pk=pk)
    if orden.estado != Orden.PENDIENTE:
        messages.error(request, "La orden ya está en cocina; no se pueden agregar productos.")
        return redirect("operativo:detalle_orden", pk=pk)
    productos_qs = Producto.objects.filter(disponible=True, sucursal=orden.sucursal)
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


TRANSICIONES_MESERO = {
    Orden.CANCELADA: {Orden.PENDIENTE},
}


@require_POST
@rol_requerido(*ROLES_MESERO)
def solicitar_cuenta(request, pk):
    orden = get_object_or_404(filtrar(Orden.objects, request, "sucursal__restaurante"), pk=pk)
    if orden.estado != Orden.LISTA:
        messages.error(request, "Solo se puede pedir la cuenta de una orden lista y servida.")
    elif orden.cuenta_solicitada_en is None:
        orden.cuenta_solicitada_en = timezone.now()
        orden.save(update_fields=["cuenta_solicitada_en", "actualizado_en"])
        destino = f"la mesa {orden.mesa.numero}" if orden.mesa_id else f"la orden #{orden.pk}"
        messages.success(request, f"Cuenta de {destino} enviada a caja.")
    return redirect("operativo:detalle_orden", pk=pk)


@rol_requerido(*ROLES_MESERO)
@require_POST
@rol_requerido(*ROLES_MESERO)
def cambiar_estado_orden(request, pk):
    orden = get_object_or_404(filtrar(Orden.objects, request, "sucursal__restaurante"), pk=pk)
    form = CambiarEstadoOrdenForm(request.POST)
    if form.is_valid():
        nuevo = form.cleaned_data["estado"]
        if orden.estado not in TRANSICIONES_MESERO.get(nuevo, set()):
            messages.error(request, "Ese cambio de estado no está permitido para esta orden.")
            return redirect("operativo:detalle_orden", pk=pk)
        try:
            orden.cambiar_estado(nuevo)
        except TransicionOrdenInvalida as error:
            messages.error(request, error.messages[0])
            return redirect("operativo:detalle_orden", pk=pk)
    return redirect("operativo:detalle_orden", pk=pk)


@rol_requerido(*ROLES_MESERO)
def generar_qr(request, mesa_id):
    mesa = get_object_or_404(filtrar(Mesa.objects, request, "sucursal__restaurante"), pk=mesa_id)
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
