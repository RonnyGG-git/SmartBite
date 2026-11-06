from django.core.exceptions import ValidationError
from django.utils import timezone

from operativo.models import Orden

MINUTOS_MAXIMOS = 240


def _accion_no_aplica():
    return ValidationError("Esa acción ya no aplica al estado actual de la orden.", code="accion_no_aplica")


def iniciar_preparacion(orden, minutos):
    if orden.estado != Orden.PENDIENTE:
        raise _accion_no_aplica()
    if not isinstance(minutos, int) or not 1 <= minutos <= MINUTOS_MAXIMOS:
        raise ValidationError("Indica un tiempo estimado de preparación válido.", code="tiempo_invalido")
    return orden.cambiar_estado(
        Orden.EN_PREPARACION,
        tiempo_estimado_min=minutos,
        preparacion_iniciada_en=timezone.now(),
    )


def marcar_lista(orden):
    if orden.estado != Orden.EN_PREPARACION:
        raise _accion_no_aplica()
    return orden.cambiar_estado(Orden.LISTA)
