"""Motor de recomendación del Asistente de Cocina.

Funciones puras (sin Django, sin base de datos) para limpiar la consulta,
corregir tipografías y mapear el lenguaje natural a los filtros del
modelo. La búsqueda TF-IDF (Fase 2) se apoya en este módulo.

Dos formas de importar, y la diferencia importa:

    from asistente_cocina.motor import normalizar        -> el MÓDULO
    from asistente_cocina.motor.normalizar import normalizar  -> la FUNCIÓN
    from asistente_cocina.motor import diccionarios, corregir_tipeo

El módulo `normalizar` y su función `normalizar()` comparten nombre a
propósito (es lo que pide la especificación), así que aquí NO se reexporta
la función con el nombre del módulo: hacerlo sobrescribiría el atributo y
`import asistente_cocina.motor.normalizar` devolvería la función en lugar
del módulo.
"""

from . import diccionarios, filtros, normalizar
from .buscador import STOPWORDS, Buscador, Sugerencia
from .diccionarios import PESOS, UMBRAL_MINIMO
from .filtros import aplicar_sinonimos, extraer_filtros
from .normalizar import corregir_tipeo

__all__ = [
    "PESOS",
    "STOPWORDS",
    "UMBRAL_MINIMO",
    "Buscador",
    "Sugerencia",
    "aplicar_sinonimos",
    "corregir_tipeo",
    "diccionarios",
    "extraer_filtros",
    "filtros",
    "normalizar",
]
