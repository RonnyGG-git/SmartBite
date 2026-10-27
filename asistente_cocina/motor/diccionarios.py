"""Diccionarios y hiperparámetros del motor de recomendación.

Vive fuera de Django a propósito: son datos puros, no modelos. Así se
pueden probar sin base de datos y sin cargar el proyecto.

Todo el mapeo está en minúsculas porque `normalizar.normalizar()` entrega
el texto ya en minúsculas y sin tildes: comparar "Postre" contra una
consulta normalizada nunca casaría si aquí se guardara con mayúscula.
"""

# Un mismo concepto se dice de varias formas. La clave es lo que el
# usuario escribe (normalizado) y el valor es el código canónico del modelo.
CATEGORIAS = {
    "entrada": "ENTRADA",
    "entrantes": "ENTRADA",
    "aperitivo": "ENTRADA",
    "plato fuerte": "PLATO_FUERTE",
    "plato principal": "PLATO_FUERTE",
    "principal": "PLATO_FUERTE",
    "postre": "POSTRE",
    "dulce": "POSTRE",
    "dulces": "POSTRE",
    "bebida": "BEBIDA",
    "bebidas": "BEBIDA",
    "refresco": "BEBIDA",
    "acompanamiento": "ACOMPANANTE",
    "acompanante": "ACOMPANANTE",
    "guarnicion": "ACOMPANANTE",
}

DIFICULTADES = {
    "facil": "FACIL",
    "sencillo": "FACIL",
    "simple": "FACIL",
    "rapido": "FACIL",
    "media": "MEDIA",
    "intermedio": "MEDIA",
    "dificil": "DIFICIL",
    "complicado": "DIFICIL",
    "elaborado": "DIFICIL",
}

# El usuario nombra el ingrediente como le sale, la receta lo guarda como lo
# tiene la despensa. Sin esta tabla "lechera" nunca encontraría la receta
# que usa "leche condensada".
SINONIMOS_INGREDIENTE = {
    "lechera": "leche condensada",
    "leche condensada": "leche condensada",
    "chocolate": "chocolate",
    "cacao": "chocolate",
    "arroz": "arroz",
    "huevo": "huevo",
    "huevos": "huevo",
    "tomate": "tomate",
    "jitomate": "tomate",
    "papa": "papa",
    "patata": "papa",
    "papas": "papa",
    "cebolla": "cebolla",
    "ajo": "ajo",
    "pollo": "pollo",
    "carne": "carne de res",
    "res": "carne de res",
    "pescado": "pescado",
    "mariscos": "pescado",
    "queso": "queso",
    "cuajo": "queso",
    "mantequilla": "mantequilla",
    "harina": "harina",
    "azucar": "azucar",
    "sal": "sal",
}

# Pesos de la puntuación final. Suman 1.0. "similitud" domina porque la
# consulta en lenguaje natural es la señal principal; el resto son filtros
# que el usuario+aún no pidió explícitamente.
PESOS = {
    "similitud": 0.45,
    "ingredientes": 0.25,
    "categoria": 0.10,
    "dificultad": 0.12,
    "tiempo": 0.08,
}

# Por debajo de esto la receta se descarta: aunque encaje en algo, la
# coincidencia es tan baja que solo genera ruido en la respuesta.
UMBRAL_MINIMO = 0.25
