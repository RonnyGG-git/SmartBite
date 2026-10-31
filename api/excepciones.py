from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError
from rest_framework.fields import get_error_detail
from rest_framework.views import exception_handler


def _primer_error(detalle, codigos):
    if isinstance(detalle, dict):
        clave = next(iter(detalle))
        return _primer_error(detalle[clave], codigos[clave])
    if isinstance(detalle, list):
        return _primer_error(detalle[0], codigos[0])
    return str(detalle), codigos


def manejador_de_errores(exc, context):
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
