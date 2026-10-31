from __future__ import annotations

import re

from .diccionarios import CATEGORIAS, DIFICULTADES, SINONIMOS_INGREDIENTE

_TIEMPO = re.compile(r"(\d+)\s*(min|mins|minuto|minutos)\b")

_NGRAMAS = (3, 2, 1)


def aplicar_sinonimos(texto: str) -> str:
    if not texto:
        return ""

    resultado = texto
    for coloquial in sorted(SINONIMOS_INGREDIENTE, key=len, reverse=True):
        canonico = SINONIMOS_INGREDIENTE[coloquial]
        if coloquial == canonico:
            continue
        resultado = re.sub(rf"\b{re.escape(coloquial)}\b", canonico, resultado)
    return resultado


def _encontrar_categoria(texto: str) -> str | None:
    for palabra, codigo in CATEGORIAS.items():
        if re.search(rf"\b{re.escape(palabra)}\b", texto):
            return codigo
    return None


def _encontrar_dificultad(texto: str) -> str | None:
    for palabra, codigo in DIFICULTADES.items():
        if re.search(rf"\b{re.escape(palabra)}\b", texto):
            return codigo
    return None


def _encontrar_tiempo_max(texto: str) -> int | None:
    coincidencia = _TIEMPO.search(texto)
    return int(coincidencia.group(1)) if coincidencia else None


def _encontrar_ingredientes(texto: str, ingredientes_conocidos: set[str]) -> list[str]:
    if not texto or not ingredientes_conocidos:
        return []

    palabras = texto.split()
    encontrados: list[str] = []
    for tamano in _NGRAMAS:
        for inicio in range(len(palabras) - tamano + 1):
            frase = " ".join(palabras[inicio:inicio + tamano])
            if frase in ingredientes_conocidos and frase not in encontrados:
                encontrados.append(frase)

    posicion = {palabra: indice for indice, palabra in enumerate(palabras)}
    encontrados.sort(key=lambda ing: posicion.get(ing.split()[0], 0))
    return encontrados


def extraer_filtros(texto: str, ingredientes_conocidos: set[str]) -> dict:
    texto = texto or ""
    return {
        "categoria": _encontrar_categoria(texto),
        "dificultad": _encontrar_dificultad(texto),
        "tiempo_max": _encontrar_tiempo_max(texto),
        "ingredientes": _encontrar_ingredientes(texto, ingredientes_conocidos),
    }
