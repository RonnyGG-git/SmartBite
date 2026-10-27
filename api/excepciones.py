from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.fields import get_error_detail
from rest_framework.views import exception_handler


def _primer_error(detalle, codigos):
    """El primer mensaje (y su código) de un error de validación anidado."""
    if isinstance(detalle, dict):
        clave = next(iter(detalle))
        return _primer_error(detalle[clave], codigos[clave])
    if isinstance(detalle, list):
        return _primer_error(detalle[0], codigos[0])
    return str(detalle), codigos


def manejador_de_errores(exc, context):
    """Formato único de error de la API: {"detail": ..., "code": ...}.

    Los errores de validación de campos agregan "errores" con el detalle por
    campo. El código HTTP lo decide DRF (400, 401, 403, 404, 405...).

    La ValidationError de Django (la que lanza el dominio sin depender de DRF,
    por ejemplo una transición de orden inválida) se convierte en la de DRF,
    conservando mensajes y códigos: sale como 400 en vez de 500. Cualquier
    otra excepción no reconocida sigue siendo 500 (no se maquillan bugs).
    """
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(detail=get_error_detail(exc))
    respuesta = exception_handler(exc, context)
    if respuesta is None:
        return None

    if isinstance(exc, ValidationError):
        mensaje, codigo = _primer_error(exc.detail, exc.get_codes())
        datos = {"detail": mensaje, "code": codigo}
        if isinstance(exc.detail, dict) and set(exc.detail) != {"non_field_errors"}:
            datos = {"detail": "Los datos enviados no son válidos.", "code": "invalid", "errores": respuesta.data}
        respuesta.data = datos
    elif isinstance(respuesta.data, dict) and "detail" in respuesta.data:
        detalle = respuesta.data["detail"]
        respuesta.data = {"detail": str(detalle), "code": getattr(detalle, "code", "error")}
    return respuesta
