import json
import uuid

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from core.mixins import RoleRequiredMixin, rol_requerido
from core.tenancy import filtrar
from restaurantes.models import Sucursal

from .conversacion import Agente, iniciar_llamada
from .models import Llamada

ROLES_AGENTE = ["ADMINISTRADOR"]
MAX_CARACTERES_TURNO = 500


def _leer_json(request):
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return {}


def _respuesta(llamada, respuesta):
    return JsonResponse({
        "llamada": llamada.pk,
        "texto": respuesta.texto,
        "finalizar": respuesta.finalizar,
        "fase": llamada.fase,
        "orden": llamada.orden_id,
    })


def _llamada_demo(request, pk):
    return get_object_or_404(
        filtrar(Llamada.objects.select_related("sucursal__restaurante"), request, "sucursal__restaurante"),
        pk=pk, canal=Llamada.CANAL_DEMO,
    )


class SimuladorView(RoleRequiredMixin, TemplateView):
    roles_permitidos = ROLES_AGENTE
    template_name = "agente_telefonico/simulador.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["sucursales"] = filtrar(
            Sucursal.objects.filter(activo=True).select_related("restaurante"), self.request, "restaurante"
        )
        return contexto


@require_POST
@rol_requerido(*ROLES_AGENTE)
def demo_iniciar(request):
    datos = _leer_json(request)
    sucursal = get_object_or_404(
        filtrar(Sucursal.objects.filter(activo=True), request, "restaurante"), pk=datos.get("sucursal") or 0
    )
    telefono = "".join(c for c in str(datos.get("telefono", "")) if c.isdigit() or c == "+")[:20]
    llamada, _ = iniciar_llamada(
        sucursal, f"demo-{uuid.uuid4().hex}", canal=Llamada.CANAL_DEMO, telefono_origen=telefono
    )
    return _respuesta(llamada, Agente(llamada).iniciar())


@require_POST
@rol_requerido(*ROLES_AGENTE)
def demo_turno(request, pk):
    llamada = _llamada_demo(request, pk)
    texto = str(_leer_json(request).get("texto", ""))[:MAX_CARACTERES_TURNO]
    agente = Agente(llamada)
    respuesta = agente.procesar(texto)
    return _respuesta(agente.llamada, respuesta)


@require_POST
@rol_requerido(*ROLES_AGENTE)
def demo_colgar(request, pk):
    llamada = _llamada_demo(request, pk)
    Agente(llamada).colgar()
    llamada.refresh_from_db()
    return JsonResponse({"llamada": llamada.pk, "estado": llamada.estado})
