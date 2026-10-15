"""Servicios del Asistente de Cocina.

El asistente es la capa que explica al chef qué está pasando con un pedido:
qué platillos lleva, qué insumos consume cada receta, cuáles no alcanzan
y en qué estado está la orden. Vive en `services.py` y no en `views.py` ni
en `models.py` por dos razones:

1. La capa de API lo consumirá sin arrastrar vistas ni plantillas.
2. La lógica del asistente es lectura y análisis; no debe poder mutar la
   orden ni el inventario. Escribir es trabajo del dominio, y el dominio ya
   tiene su única puerta de entrada: `Orden.cambiar_estado()`.

FALLAR RÁPIDO (decisión de diseño)
----------------------------------
`consultar()` lanza `NotImplementedError` en vez de devolver un diccionario
mock. Un mock en un contrato de dominio es peor que no tener contrato: el
equipo de API construiría contra una forma de datos inventada, y en
producción empezaría a recibir `{"sugerencia": ...}` vacío como si fuera
una respuesta válida. Fallar ruidoso desde el día uno es más barato que un
fallo silencioso dentro de dos semanas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Código estable para que la API pueda mapearlo sin leer mensajes en texto.
CODIGO_ASISTENTE_NO_IMPLEMENTADO = "asistente_no_implementado"


class AsistenteNoImplementado(NotImplementedError):
    """El asistente todavía no tiene cerebro; el contrato sí existe.

    Hereda de `NotImplementedError` para que quien lo reciba sepa que es un
    hueco planificado y no un fallo de infraestructura.
    """

    code = CODIGO_ASISTENTE_NO_IMPLEMENTADO

    def __init__(self, mensaje: str = "La integracion con el asistente de cocina esta pendiente.") -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


@dataclass(frozen=True)
class ConsultaAsistente:
    """Peticion de analisis para una orden.

    Congelada (`frozen=True`) a propósito: es una petición de solo lectura,
    y que nadie pueda mutarla después de construirla evita estados
    intermedios raros al pasarla entre capas.
    """

    orden_id: int
    # Datos y texto ya resueltos por el dominio. El servicio los rellena
    # desde `inventario.services` y `Orden`; hoy van vacíos porque todavía
    # no hay cerebro que los consuma.
    datos: dict[str, Any] = field(default_factory=dict)
    contexto: str = ""


@dataclass(frozen=True)
class RespuestaAsistente:
    """Respuesta que consumirá el endpoint de la API.

    Los campos son deliberadamente los mínimos: lo que un chef necesita leer
    de un vistazo. Agregar campos después es compatible; cambiar el
    significado de uno existente no lo sería.
    """

    orden_id: int
    # Texto corto para el ticket de cocina.
    resumen: str
    # Platillos de la orden, en el orden en que se ingresaron.
    platillos: list[str] = field(default_factory=list)
    # Insumos que no alcanzan, como "Arroz x3".
    faltantes: list[str] = field(default_factory=list)
    # Sugerencia accionable del asistente. Vacía hasta que exista el
    # cerebro; el contrato ya la reserva para no romper compatibilidad.
    sugerencia: str = ""


def consultar(consulta: ConsultaAsistente) -> RespuestaAsistente:
    """Analiza una orden y devuelve lo que la cocina necesita saber.

    Punto de entrada único del asistente. La API lo llamará con una
    `ConsultaAsistente` y recibirá una `RespuestaAsistente`.

    Qué hace, por su intención (aún sin implementar):
      1. Cargar la orden y sus platillos.
      2. Reutilizar `inventario.services.calcular_insumos_requeridos()`
         para saber cuánto consume cada receta, en vez de recalcularlo.
      3. Cruzar ese total contra el stock real para listar los faltantes y
         avisar al chef antes de que empiece a cocinar.
      4. Redactar una sugerencia accionable (cambiar de platillo, pausar,
         avisar al mesero).

    Levanta:
        ValidationError: si `consulta.orden_id` no corresponde a una orden.
        AsistenteNoImplementado: siempre, por ahora. Es deliberado: el
            contrato queda fijado y verificable antes de programar el
            modelo de lenguaje.
    """
    raise AsistenteNoImplementado()
