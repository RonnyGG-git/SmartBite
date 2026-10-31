import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator, URLValidator

telefono_validator = RegexValidator(
    regex=r"^\+?[\d\s\-()]{7,30}$",
    message="Ingresa un teléfono válido (solo dígitos, espacios, +, - o paréntesis).",
    code="telefono_invalido",
)

url_publica_validator = URLValidator(
    schemes=["http", "https"],
    message="Ingresa una URL válida que empiece por http:// o https://.",
)

nif_validator = RegexValidator(
    regex=r"^\d{6,10}([.\-]\d{1,3})?([\-]?[0-9A-Za-z])?$",
    message="Ingresa un NIF/RUT válido (solo números, guiones o puntos y letra de control).",
    code="nif_invalido",
)


def limpiar_telefono(valor):
    if not valor:
        return ""
    limpio = re.sub(r"[^\d+]", "", valor.strip())
    if limpio.startswith("+"):
        return "+" + re.sub(r"\D", "", limpio[1:])
    return re.sub(r"\D", "", limpio)


def validar_telefono(valor):
    if valor in (None, ""):
        return ""
    try:
        telefono_validator(valor.strip())
    except ValidationError:
        raise ValidationError(
            telefono_validator.message,
            code=telefono_validator.code,
        )
    return limpiar_telefono(valor)
