"""Manejador global de errores para la API.

Conecta los `django.core.exceptions.ValidationError` que lanza la capa de
dominio (operativo, inventario, ...) con las respuestas de DRF.

Por qué hace falta: el `exception_handler` de DRF solo traduce
`APIException`, `Http404` y `PermissionDenied`. Un `ValidationError` de Django
que escapa del cuerpo de una vista no lo reconoce nadie y se convierte en un
**HTTP 500**. Como el dominio no debe depender de DRF (ver
`operativo.models.TransicionOrdenInvalida`), el puente se resuelve aquí, en un
único punto, en vez de repetir try/except en cada endpoint.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# Código por defecto cuando la excepción no trae uno propio.
CODIGO_VALIDACION_POR_DEFECTO = "validation_error"


def _detalle_de(exc):
    """Mensajes del error, preservando la association campo -> mensaje.

    Un ValidationError puede construirse de dos formas:
      - ValidationError("mensaje")                  -> lista
      - ValidationError({"campo": ["err"]})         -> diccionario por campo
    Con `message_dict` el cliente recibe {"precio": ["requerido"]}, que es
    accionable; aplanar a lista perdería qué campo falló.
    """
    if hasattr(exc, "error_dict"):
        return exc.message_dict
    return exc.messages


def _codigo_de(exc):
    """Código de la excepción, o el de la primera de sus causas.

    OJO: `ValidationError` NO siempre tiene atributo `code` — solo cuando se
    construyó con un string. Los construidos con diccionario (los que lanza un
    ModelForm/forms) no lo tienen, y `exc.code` lanzaría AttributeError.
    Por eso se usa getattr con defecto.
    """
    codigo = getattr(exc, "code", None)
    if codigo:
        return codigo
    # Si no lo tiene arriba, se busca en la primera causa (errores anidados).
    if hasattr(exc, "error_list"):
        for error in exc.error_list:
            codigo = getattr(error, "code", None)
            if codigo:
                return codigo
    return CODIGO_VALIDACION_POR_DEFECTO


def custom_exception_handler(exc, context):
    """Punto de entrada único de errores de la API.

    Primero delega en DRF (para no romper APIException, 404, 403, throttling...) y
    solo si DRF no reconoce la excepción intenta traducirla a 400.

    Devolver None significa "esta excepción no es para mí" y DRF la deja
    escapar al middleware de Django (500). Ese es el comportamiento deseado
    para errores inesperados: no queremos maquillar bugs como 400.
    """
    # 1. DRF primero: respeta su propio contrato para lo que ya sabe manejar.
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    # 2. ValidationError de Django que se le escapó a DRF -> 400.
    if isinstance(exc, DjangoValidationError):
        return Response(
            {"detail": _detalle_de(exc), "code": _codigo_de(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Cualquier otra excepción: 500 sin tocar.
    return None