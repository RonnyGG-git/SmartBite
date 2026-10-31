from decimal import Decimal
from core.tenancy import RestauranteMixin, filtrar
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from core.mixins import RoleRequiredMixin, rol_requerido
from operativo.models import Orden

from . import servicios
from .forms import CobrarOrdenForm
from .models import AuditoriaCobro, Factura, Pago
from .pasarelas import FirmaInvalida, SimuladaPasarela, obtener_pasarela
from .servicios import CobroInvalido

ROLES_CAJA = ["ADMINISTRADOR", "CAJERO"]
ROLES_ENTREGA = ["ADMINISTRADOR", "CAJERO", "MESERO"]


def _ip(request):
    return request.META.get("REMOTE_ADDR")


class PagoListView(RoleRequiredMixin, ListView):
    model = Pago
    roles_permitidos = ROLES_CAJA
    template_name = "caja/pagos_list.html"
    context_object_name = "pagos"
    queryset = Pago.objects.select_related("orden", "metodo_pago", "cobrado_por")


@rol_requerido(*ROLES_CAJA)
def cobrar_orden(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    if orden.es_final:
        return redirect("operativo:detalle_orden", pk=pk)
    orden = _orden_del_restaurante(request, pk)

    if request.method == "POST":
        form = CobrarOrdenForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            metodo, monto, propina = datos["metodo_pago"], datos["monto"], datos["propina"]
            try:
                if metodo.requiere_pasarela:
                    pago, pasarela = servicios.iniciar_cobro_tarjeta(
                        orden.pk, metodo=metodo, monto=monto, propina=propina,
                        usuario=request.user, ip=_ip(request),
                    )
                    return redirect(pasarela.url_checkout(request, pago))

                servicios.registrar_pago_manual(
                    orden.pk, metodo=metodo, monto=monto, propina=propina,
                    referencia=datos["referencia_transaccion"], usuario=request.user, ip=_ip(request),
                )
            except CobroInvalido as error:
                form.add_error(None, str(error))
            else:
                recibido = datos["efectivo_recibido"]
                if recibido and recibido > monto + propina:
                    messages.info(request, f"Cambio a devolver: ${recibido - monto - propina:,.0f}")
                orden.refresh_from_db()
                if orden.estado == Orden.ENTREGADA:
                    messages.success(request, f"Orden #{orden.pk} pagada por completo.")
                    factura = Factura.objects.filter(orden=orden).first()
                    if factura:
                        return redirect("caja:factura_detalle", pk=factura.pk)
                    return redirect("operativo:mesas_list")
                messages.success(request, f"Pago registrado. Saldo pendiente: ${servicios.saldo_pendiente(orden):,.0f}")
                return redirect("caja:cobrar_orden", pk=orden.pk)
    else:
        form = CobrarOrdenForm(initial={"monto": max(servicios.saldo_disponible(orden), Decimal("0"))})

    return render(request, "caja/registrar_pago.html", {
        "orden": orden, "form": form, "saldo": servicios.saldo_pendiente(orden),
        "pagos_orden": orden.pagos.select_related("metodo_pago").all(),
    })


@login_required
def retorno_pago(request):
    """A donde vuelve el cliente tras la pasarela. El estado real lo fija el webhook."""
    pago = get_object_or_404(Pago, referencia_pasarela=request.GET.get("ref", ""))
    return render(request, "caja/retorno_pago.html", {"pago": pago})


@csrf_exempt
@require_POST
def webhook(request, proveedor):
    """Recibe eventos de la pasarela. Sin CSRF ni login: se autentica con el checksum."""
    try:
        pasarela = obtener_pasarela(proveedor)
    except KeyError:
        return HttpResponseBadRequest("proveedor desconocido")
    try:
        servicios.procesar_evento(pasarela, request.body, request.headers)
    except FirmaInvalida:
        return HttpResponse(status=400)
    return HttpResponse(status=200)  # también en duplicados: así la pasarela deja de reintentar


@login_required
def pasarela_simulada(request, referencia):
    """Pantalla de 'banco' falsa para demos sin internet."""
    pago = get_object_or_404(Pago, referencia_pasarela=referencia, proveedor="SIMULADA")
    if request.method == "POST" and pago.estado == Pago.PENDIENTE:
        pasarela = SimuladaPasarela()
        estado = "APPROVED" if request.POST.get("resultado") == "aprobar" else "DECLINED"
        servicios.procesar_evento(pasarela, pasarela.construir_evento(pago, estado), {})
        return redirect(f"/caja/pagos/retorno/?ref={referencia}")
    return render(request, "caja/pasarela_simulada.html", {"pago": pago})


@rol_requerido("ADMINISTRADOR")
def auditoria_list(request):
    registros = AuditoriaCobro.objects.select_related("orden", "pago", "usuario")
    accion, usuario, desde = request.GET.get("accion"), request.GET.get("usuario"), request.GET.get("desde")
    if accion:
        registros = registros.filter(accion=accion)
    if usuario:
        registros = registros.filter(usuario__nombre__icontains=usuario)
    if desde:
        registros = registros.filter(creado_en__date__gte=desde)
    return render(request, "caja/auditoria_list.html", {
        "registros": registros[:300], "acciones": AuditoriaCobro.ACCION_CHOICES,
        "filtros": {"accion": accion or "", "usuario": usuario or "", "desde": desde or ""},
    })


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
    queryset = Orden.objects.filter(estado=Orden.ENTREGADA).select_related("mesa", "cliente").prefetch_related("pagos")
