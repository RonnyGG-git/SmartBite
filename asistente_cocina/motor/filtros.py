"""Extracción de filtros a partir de una consulta en lenguaje natural.

Recibe texto YA normalizado (ver `normalizar.normalizar`): por eso aquí no
se vuelve a normalizar y todas las búsquedas comparan contra claves en
minúsculas y sin tildes.

Devuelve un diccionario de filtros, nunca objetos del modelo: así esta
capa se puede probar sin base de datos y el buscador la puede combinar con
recetas que vengan de donde sea.
"""

from __future__ import annotations

import re

from .diccionarios import CATEGORIAS, DIFICULTADES, SINONIMOS_INGREDIENTE

# "30 min", "30min", "30 minutos", "45 mins"
_TIEMPO = re.compile(r"(\d+)\s*(min|mins|minuto|minutos)\b")

# Se buscan primero las frases más largas para que "leche condensada" gane
# a "leche". Es un greedy match por longitud, no un orden de aparición.
_NGRAMAS = (3, 2, 1)


def aplicar_sinonimos(texto: str) -> str:
    """Sustituye nombres colloquiales de ingredientes por los canónicos.

    "lechera" -> "leche condensada". Se usa `\\b` para no tocar palabras que
    solo contengan el término: "pollo" no debe convertirse dentro de
    "apollonico".
    """
    if not texto:
        return ""

    resultado = texto
    # De la expresión más larga a la más corta, para que "leche condensada"
    # se sustituya antes que "leche".
    for coloquial in sorted(SINONIMOS_INGREDIENTE, key=len, reverse=True):
        canonico = SINONIMOS_INGREDIENTE[coloquial]
        if coloquial == canonico:
            continue
        resultado = re.sub(rf"\b{re.escape(coloquial)}\b", canonico, resultado)
    return resultado


def _encontrar_categoria(texto: str) -> str | None:
    """Devuelve el código de categoría o None si la consulta no lo dice."""
    for palabra, codigo in CATEGORIAS.items():
        # \b para que "principal" no entre dentro de "principalmente".
        if re.search(rf"\b{re.escape(palabra)}\b", texto):
            return codigo
    return None


def _encontrar_dificultad(texto: str) -> str | None:
    for palabra, codigo in DIFICULTADES.items():
        if re.search(rf"\b{re.escape(palabra)}\b", texto):
            return codigo
    return None


def _encontrar_tiempo_max(texto: str) -> int | None:
    """Extrae el límite de tiempo en minutos, si la consulta lo menciona."""
    coincidencia = _TIEMPO.search(texto)
    return int(coincidencia.group(1)) if coincidencia else None


def _encontrar_ingredientes(texto: str, ingredientes_conocidos: set[str]) -> list[str]:
    """Cruza la consulta con el inventario de ingredientes disponibles.

    Se recorren n-gramas de 3, luego 2 y luego 1 palabra. El orden importa:
    sin él, "leche condensada" se detectaría primero como "leche" y la
    receta que exige el condensado completo se descartaría.
    """
    if not texto or not ingredientes_conocidos:
        return []

    palabras = texto.split()
    encontrados: list[str] = []
    for tamano in _NGRAMAS:
        for inicio in range(len(palabras) - tamano + 1):
            frase = " ".join(palabras[inicio:inicio + tamano])
            if frase in ingredientes_conocidos and frase not in encontrados:
                encontrados.append(frase)

    # Orden estable y legible: el orden de aparición en la consulta, no el
    # del bucle de n-gramas, que devolvería "leche" antes que
    # "leche condensada".
    posicion = {palabra: indice for indice, palabra in enumerate(palabras)}
    encontrados.sort(key=lambda ing: posicion.get(ing.split()[0], 0))
    return encontrados


def extraer_filtros(texto: str, ingredientes_conocidos: set[str]) -> dict:
    """Traduce una consulta normalizada a filtros estructurados.

    Devuelve siempre las cuatro claves; valen None cuando la consulta no
    menciona el filtro, para que el llamador distinga "no dijo" de "dijo
    que no".
    """
    texto = texto or ""
    return {
        "categoria": _encontrar_categoria(texto),
        "dificultad": _encontrar_dificultad(texto),
        "tiempo_max": _encontrar_tiempo_max(texto),
        "ingredientes": _encontrar_ingredientes(texto, ingredientes_conocidos),
    }
