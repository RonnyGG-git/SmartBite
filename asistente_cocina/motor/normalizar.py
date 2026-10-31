from __future__ import annotations

import re
import unicodedata

_CARACTERES_PERMITIDOS = re.compile(r"[^a-z0-9ñ\s]")
_ESPACIOS = re.compile(r"\s+")

LONGITUD_MINIMA_TIPOEO = 3

UMBRAL_TIPOEO = 85


def normalizar(texto: str) -> str:
    if not texto:
        return ""

    sin_tildes = "".join(
        caracter for caracter in unicodedata.normalize("NFKD", texto.lower())
        if not unicodedata.combining(caracter)
    )
    sin_puntuacion = _CARACTERES_PERMITIDOS.sub(" ", sin_tildes)
    return _ESPACIOS.sub(" ", sin_puntuacion).strip()


def corregir_tipeo(texto: str, vocabulario: set[str], umbral: int = UMBRAL_TIPOEO) -> str:
    from rapidfuzz import fuzz, process

    if not texto:
        return ""

    palabras = texto.split()
    conocidas = set(vocabulario)
    desplazamiento: dict[str, str] = {}

    for indice, palabra in enumerate(palabras):
        if palabra in conocidas or len(palabra) <= LONGITUD_MINIMA_TIPOEO:
            continue
        if palabra.isdigit():
            continue

        candidatas = [candidata for candidata in conocidas if len(candidata) <= len(palabra) + 2]
        if not candidatas:
            continue

        mejor = process.extractOne(palabra, candidatas, scorer=fuzz.ratio)
        if mejor is None:
            continue
        coincidencia, puntuacion = mejor[0], mejor[1]
        if puntuacion >= umbral:
            palabras[indice] = coincidencia
            desplazamiento[palabra] = coincidencia

    return " ".join(palabras)
