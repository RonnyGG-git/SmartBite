from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from cliente.forms import ReservaForm, RetroalimentacionForm
from cliente.views import _sucursales_publicas
from operativo.models import Mesa, Reserva
from operativo.services import cancelar_reserva, crear_reserva, horarios_alternativos, sincronizar_reservas

from .serializers_gestion import OpinionSerializer, ReservaPublicaSerializer
from .views_cuenta import errores_de_form


class Publico:
    permission_classes = [AllowAny]
    authentication_classes = []


def _reserva(codigo):
    return get_object_or_404(
        Reserva.objects.select_related("mesa__sucursal__restaurante"), codigo=(codigo or "").strip().upper()
    )


@extend_schema(tags=["publico"], responses=ReservaPublicaSerializer)
class ReservarView(Publico, generics.GenericAPIView):
    serializer_class = ReservaPublicaSerializer

    def post(self, request, pk):
        sucursal = get_object_or_404(_sucursales_publicas(), pk=pk)
        form = ReservaForm(data=request.data)
        if not form.is_valid():
            raise errores_de_form(form)
        datos = form.cleaned_data
        try:
            reserva = crear_reserva(sucursal, datos["fecha_hora"], datos["num_personas"], datos["nombre"], datos["telefono"])
        except DjangoValidationError as error:
            alternativas = []
            if error.code == "sin_mesa":
                alternativas = [h.isoformat() for h in horarios_alternativos(sucursal, datos["fecha_hora"], datos["num_personas"])]
            return Response(
                {"detail": error.messages[0], "code": error.code or "invalid", "alternativas": alternativas},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ReservaPublicaSerializer(_reserva(reserva.codigo)).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["publico"], responses=ReservaPublicaSerializer)
class ReservaPublicaView(Publico, generics.GenericAPIView):
    serializer_class = ReservaPublicaSerializer

    def get(self, request, codigo):
        reserva = _reserva(codigo)
        sincronizar_reservas(Reserva.objects.filter(pk=reserva.pk))
        return Response(ReservaPublicaSerializer(_reserva(codigo)).data)

    def post(self, request, codigo):
        reserva = _reserva(codigo)
        try:
            cancelar_reserva(reserva)
        except DjangoValidationError as error:
            raise ValidationError(error.messages[0], code=error.code or "invalid")
        return Response(ReservaPublicaSerializer(_reserva(codigo)).data)


@extend_schema(tags=["publico"], responses=OpinionSerializer)
class OpinarView(Publico, generics.GenericAPIView):
    serializer_class = OpinionSerializer

    def post(self, request):
        form = RetroalimentacionForm(data=request.data)
        if not form.is_valid():
            raise errores_de_form(form)
        opinion = form.save(commit=False)
        mesa_id = str(request.data.get("mesa") or "")
        opinion.mesa = Mesa.objects.filter(pk=int(mesa_id), activa=True).first() if mesa_id.isdigit() else None
        opinion.save()
        return Response(OpinionSerializer(opinion).data, status=status.HTTP_201_CREATED)
