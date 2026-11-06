from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.mixins import rol_requerido
from domicilio import services
from domicilio.models import DireccionCliente, Domicilio, PerfilCliente

from .forms import DireccionForm, PerfilClienteForm

ROLES_CLIENTE = ["CLIENTE"]

DOMICILIOS = Domicilio.objects.select_related(
    "orden__sucursal__restaurante", "domiciliario"
).prefetch_related("orden__detalles__producto")

PASOS = [
    (Domicilio.SOLICITADO, "Solicitado"),
    (Domicilio.CONFIRMADO, "Confirmado"),
    (Domicilio.EN_COCINA, "En cocina"),
    (Domicilio.LISTO_PARA_RECOGER, "Listo"),
    (Domicilio.ASIGNADO, "Asignado"),
    (Domicilio.EN_CAMINO, "En camino"),
    (Domicilio.ENTREGADO, "Entregado"),
]


def es_cliente(usuario):
    return usuario.is_authenticated and usuario.rol_id is not None and usuario.rol.nombre == "CLIENTE"


def perfil_de(usuario):
    perfil, _ = PerfilCliente.objects.get_or_create(usuario=usuario)
    return perfil


def inicio(request):
    return render(request, "cliente/inicio.html", {"es_cliente": es_cliente(request.user)})


def escanear(request):
    return render(request, "cliente/escanear.html")


@rol_requerido(*ROLES_CLIENTE)
def cuenta(request):
    usuario = request.user
    perfil = perfil_de(usuario)
    if request.method == "POST":
        form = PerfilClienteForm(request.POST)
        if form.is_valid():
            datos = form.cleaned_data
            with transaction.atomic():
                usuario.nombre = datos["nombre"].strip()
                usuario.save(update_fields=["nombre"])
                perfil.telefono = datos["telefono"].strip()
                perfil.documento = datos["documento"].strip()
                perfil.save(update_fields=["telefono", "documento", "actualizado_en"])
            messages.success(request, "Tus datos quedaron guardados.")
            return redirect("cliente:cuenta")
    else:
        form = PerfilClienteForm(initial={"nombre": usuario.nombre, "telefono": perfil.telefono, "documento": perfil.documento})
    return render(request, "cliente/cuenta.html", {
        "form": form,
        "direcciones": DireccionCliente.objects.filter(usuario=usuario),
    })


def _marcar_principal(usuario, direccion):
    otras = DireccionCliente.objects.filter(usuario=usuario).exclude(pk=direccion.pk)
    if direccion.principal or not otras.exists():
        otras.update(principal=False)
        if not direccion.principal:
            direccion.principal = True
            direccion.save(update_fields=["principal"])


@rol_requerido(*ROLES_CLIENTE)
def direccion(request, pk=None):
    existente = get_object_or_404(DireccionCliente, pk=pk, usuario=request.user) if pk else None
    if request.method == "POST":
        form = DireccionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                obj = existente or DireccionCliente(usuario=request.user)
                for campo, valor in form.cleaned_data.items():
                    setattr(obj, campo, valor.strip() if isinstance(valor, str) else valor)
                obj.save()
                _marcar_principal(request.user, obj)
            messages.success(request, "Dirección guardada.")
            return redirect(request.GET.get("volver") or "cliente:cuenta")
    elif existente:
        form = DireccionForm(initial={
            campo: getattr(existente, campo) for campo in DireccionForm.base_fields
        })
    else:
        form = DireccionForm()
    return render(request, "cliente/direccion.html", {"form": form, "existente": existente})


@rol_requerido(*ROLES_CLIENTE)
@require_POST
def direccion_eliminar(request, pk):
    obj = get_object_or_404(DireccionCliente, pk=pk, usuario=request.user)
    era_principal = obj.principal
    obj.delete()
    if era_principal:
        siguiente = DireccionCliente.objects.filter(usuario=request.user).first()
        if siguiente:
            siguiente.principal = True
            siguiente.save(update_fields=["principal"])
    messages.success(request, "Dirección eliminada.")
    return redirect("cliente:cuenta")


@rol_requerido(*ROLES_CLIENTE)
def domicilios(request):
    return render(request, "cliente/domicilios.html", {
        "domicilios": DOMICILIOS.filter(cliente=request.user).order_by("-creado_en")[:30],
    })


def _pasos(domicilio):
    if domicilio.estado == Domicilio.CANCELADO:
        return []
    actual = [estado for estado, _ in PASOS].index(domicilio.estado)
    return [
        {"texto": texto, "clase": "is-done" if i < actual else ("is-current" if i == actual else "")}
        for i, (_, texto) in enumerate(PASOS)
    ]


@rol_requerido(*ROLES_CLIENTE)
def domicilio_detalle(request, pk):
    domicilio = get_object_or_404(DOMICILIOS, pk=pk, cliente=request.user)
    return render(request, "cliente/domicilio.html", {
        "domicilio": domicilio,
        "orden": domicilio.orden,
        "sucursal": domicilio.orden.sucursal,
        "pasos": _pasos(domicilio),
        "puede_cancelar": domicilio.estado == Domicilio.SOLICITADO,
    })


@rol_requerido(*ROLES_CLIENTE)
def domicilio_estado(request, pk):
    d = get_object_or_404(Domicilio, pk=pk, cliente=request.user)
    return JsonResponse({
        "estado": d.estado,
        "estado_texto": d.get_estado_display(),
        "moto": [float(d.lat_actual), float(d.lng_actual)] if d.lat_actual is not None and d.lng_actual is not None else None,
        "final": d.estado in (Domicilio.ENTREGADO, Domicilio.CANCELADO),
    })


@rol_requerido(*ROLES_CLIENTE)
@require_POST
def domicilio_cancelar(request, pk):
    domicilio = get_object_or_404(Domicilio, pk=pk, cliente=request.user)
    try:
        services.cancelar_por_cliente(domicilio, request.user)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Cancelaste el pedido.")
    return redirect("cliente:domicilio", pk=pk)
