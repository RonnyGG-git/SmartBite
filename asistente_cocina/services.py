from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from django.core.exceptions import ValidationError

CODIGO_ASISTENTE_NO_IMPLEMENTADO = "asistente_no_implementado"


class AsistenteNoImplementado(NotImplementedError):
    code = CODIGO_ASISTENTE_NO_IMPLEMENTADO

    def __init__(self, mensaje: str = "La integracion con el asistente de cocina esta pendiente.") -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


@dataclass(frozen=True)
class ConsultaAsistente:
    orden_id: int
    datos: dict[str, Any] = field(default_factory=dict)
    contexto: str = ""


@dataclass(frozen=True)
class RespuestaAsistente:
    orden_id: int
    resumen: str
    platillos: list[str] = field(default_factory=list)
    faltantes: list[str] = field(default_factory=list)
    sugerencia: str = ""


def consultar(consulta: ConsultaAsistente) -> RespuestaAsistente:
    raise AsistenteNoImplementado()
