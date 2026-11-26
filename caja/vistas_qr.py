import base64
import io
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import qrcode
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import ListView

from core.mixins import RoleRequiredMixin, rol_requerido
from core.tenancy import RestauranteMixin, filtrar
from operativo.models import Orden

from . import conf, servicios
from .models import EnlacePago, Factura, Pago
from .pasarelas import url_absoluta
from .qr import cobrar_por_qr, es_simulada, iniciar_cobro_qr, obtener_enlace_pago, pedir_pago_en_efectivo
from .servicios import CobroInvalido

ROLES_CAJA = ["ADMINISTRADOR", "CAJERO"]
CERO = Decimal("0")


def _qr_base64(texto):
    imagen = qrcode.make(texto)
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def leer_monto(texto):
    texto = (texto or "").replace("$", "").replace(" ", "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):
        texto = texto.replace(".", "")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _entero_o_decimal(valor):
    valor = Decimal(valor)
    return str(int(valor)) if valor == valor.to_integral_value() else str(valor)


@rol_requerido(*ROLES_CAJA)
def qr_cobro(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    if orden.es_final:
        return redirect("operativo:detalle_orden", pk=pk)
    enlace = obtener_enlace_pago(orden, request.user)
    ruta = reverse("caja:pagar_cliente", args=[enlace.token])
    base = conf.base_url()
    url = base.rstrip("/") + ruta if base else request.build_absolute_uri(ruta)
    return render(request, "caja/qr_cobro.html", {
        "orden": orden, "url": url, "qr": _qr_base64(url), "saldo": servicios.saldo_pendiente(orden),
        "pagos_iniciales": orden.pagos.filter(estado=Pago.APROBADO).count(),
    })


@rol_requerido(*ROLES_CAJA)
def estado_orden(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    factura = Factura.objects.filter(orden=orden).first()
    return JsonResponse({
        "saldo": float(servicios.saldo_pendiente(orden)),
        "pagada": orden.estado == Orden.ENTREGADA,
        "pagos": orden.pagos.filter(estado=Pago.APROBADO).count(),
        "efectivo": orden.enlaces_pago.filter(efectivo_solicitado_en__isnull=False).exists(),
        "factura_url": reverse("caja:factura_detalle", args=[factura.pk]) if factura else None,
    })


class FacturaListView(RestauranteMixin, RoleRequiredMixin, ListView):
    ruta_restaurante = "orden__sucursal__restaurante"
    model = Factura
    roles_permitidos = ROLES_CAJA
    template_name = "caja/facturas_list.html"
    context_object_name = "facturas"
    queryset = Factura.objects.select_related("orden")


@rol_requerido(*ROLES_CAJA)
def factura_detalle(request, pk):
    factura = get_object_or_404(filtrar(Factura.objects, request, "orden__sucursal__restaurante"), pk=pk)
    return render(request, "caja/factura.html", {"f": factura, "d": factura.detalle, "publico": False})


def _restaurante_de(orden):
    sucursal = orden.mesa.sucursal if orden.mesa_id is not None else orden.sucursal
    return sucursal.restaurante


def _enlace(token):
    return get_object_or_404(EnlacePago.objects.select_related("orden__mesa__sucursal__restaurante", "orden__sucursal__restaurante"), token=token)


def pagar_cliente(request, token):
    enlace = _enlace(token)
    orden = enlace.orden
    saldo = servicios.saldo_disponible(orden)
    factura = Factura.objects.filter(orden=orden).first()
    ctx = {
        "enlace": enlace, "orden": orden, "restaurante": _restaurante_de(orden),
        "lineas": orden.detalles.select_related("producto"), "total": orden.total, "saldo": saldo,
        "pagado": orden.total - servicios.saldo_pendiente(orden),
        "propina_sugerida": _entero_o_decimal((max(saldo, CERO) * Decimal("0.10")).quantize(Decimal("1"))),
        "monto_valor": _entero_o_decimal(saldo) if saldo > 0 else "", "propina_valor": "",
        "vencido": not enlace.vigente, "pagada": saldo <= 0 and orden.estado == Orden.ENTREGADA,
        "factura_url": reverse("caja:factura_publica", args=[token]) if factura else None,
        "modo_prueba": conf.modo_prueba(), "simulada": es_simulada(),
    }
    if ctx["vencido"] or ctx["pagada"] or orden.estado == Orden.CANCELADA:
        return render(request, "caja/pagar_cliente.html", ctx)

    intentos = servicios.intentos_en_linea_pendientes(orden).filter(cobrado_por__isnull=True)
    if request.method == "POST" and request.POST.get("accion") == "anular_intento":
        intento = intentos.filter(pk=request.POST.get("pago") or 0).first()
        if intento is not None:
            try:
                servicios.anular_pago_pendiente(
                    intento.pk, ip=request.META.get("REMOTE_ADDR"), detalle="El cliente canceló el pago sin terminar"
                )
            except CobroInvalido:
                pass
        return redirect("caja:pagar_cliente", token=token)

    ctx["intentos"] = intentos
    ctx["efectivo"] = enlace.efectivo_solicitado_en is not None
    if request.method == "POST" and request.POST.get("accion") == "efectivo":
        try:
            pedir_pago_en_efectivo(enlace)
        except CobroInvalido as error:
            ctx["error"] = str(error)
        else:
            ctx["efectivo"] = True
        return render(request, "caja/pagar_cliente.html", ctx)

    if request.method == "POST":
        ctx["monto_valor"] = request.POST.get("monto", "")
        ctx["propina_valor"] = request.POST.get("propina", "")
        monto = leer_monto(request.POST.get("monto"))
        propina = leer_monto(request.POST.get("propina")) if request.POST.get("propina", "").strip() else CERO

        if monto is None or monto <= 0:
            ctx["error"] = "Escribe un monto válido."
        elif propina is None or propina < 0:
            ctx["error"] = "La propina no es válida."
        elif monto > saldo:
            ctx["error"] = f"El monto supera lo que se debe. Máximo: ${int(saldo):,}".replace(",", ".")
        elif monto < saldo and not request.POST.get("confirmar_parcial"):
            ctx["aviso"] = {"monto": monto, "faltante": saldo - monto}
        else:
            ip = request.META.get("REMOTE_ADDR")
            try:
                if es_simulada():
                    pago = cobrar_por_qr(enlace, monto=monto, propina=propina, ip=ip)
                    destino = f"{reverse('caja:pago_listo', args=[token])}?ref={pago.referencia_pasarela}"
                else:
                    pago, pasarela = iniciar_cobro_qr(enlace, monto=monto, propina=propina, ip=ip)
                    retorno = (
                        url_absoluta(request, reverse("caja:pago_listo", args=[token]))
                        + "?" + urlencode({"ref": pago.referencia_pasarela})
                    )
                    destino = pasarela.url_checkout(request, pago, retorno=retorno)
            except CobroInvalido as error:
                ctx["error"] = str(error)
            else:
                return redirect(destino)

    return render(request, "caja/pagar_cliente.html", ctx)


def _pago_del_enlace(request, enlace):
    pago = get_object_or_404(Pago, referencia_pasarela=request.GET.get("ref", ""), orden=enlace.orden)
    return servicios.sincronizar_pago(pago, request.GET.get("id"))


def pago_listo(request, token):
    enlace = _enlace(token)
    pago = _pago_del_enlace(request, enlace)
    factura = Factura.objects.filter(orden=enlace.orden).first()
    return render(request, "caja/pago_listo.html", {
        "enlace": enlace, "pago": pago, "orden": enlace.orden, "restaurante": _restaurante_de(enlace.orden),
        "faltante": max(servicios.saldo_pendiente(enlace.orden), CERO),
        "factura_url": reverse("caja:factura_publica", args=[token]) if factura else None,
        "modo_prueba": conf.modo_prueba(),
        "estado_url": reverse("caja:estado_pago", args=[token]) + "?" + urlencode(
            {"ref": pago.referencia_pasarela, "id": request.GET.get("id", "")}
        ),
    })


def estado_pago(request, token):
    pago = _pago_del_enlace(request, _enlace(token))
    return JsonResponse({"estado": pago.estado})


def factura_publica(request, token):
    enlace = _enlace(token)
    factura = get_object_or_404(Factura, orden=enlace.orden)
    return render(request, "caja/factura.html", {"f": factura, "d": factura.detalle, "publico": True})