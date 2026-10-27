"""Normalización de texto para el motor de recomendación.

Funciones puras: no importan Django ni tocan la base de datos. Se pueden
probar y reutilizar desde cualquier sitio (tests, scripts, futuro
intento de línea de comandos).

El criterio que rige el módulo es uno solo: después de pasar por aquí, dos
textos que significan lo mismo tienen que verse exactamente iguales.
"Arroz con Pollo", "arroz  con pollo!" y "ARROZ CON POLLO" deben colapsar
al mismo string, o el índice TF-IDF los trataría como documentos distintos.
"""

from __future__ import annotations

import re
import unicodedata

# Se permite la ñ además de letras y números; el resto de puntuación se va.
_CARACTERES_PERMITIDOS = re.compile(r"[^a-z0-9ñ\s]")
_ESPACIOS = re.compile(r"\s+")

# Palabras que no vale la pena "corregir": "pan" puede ser pan, no "pano",
# y a 3 letras los errores de Levenshtein dominan sobre la señal.
LONGITUD_MINIMA_TIPOEO = 3

# Por debajo de esta similitud se considera que la palabra es correcta.
# 85 es conservador: preferimos dejar pasar un error tipográfico menor
# antes que "arreglar" una palabra correcta y destroy la búsqueda.
UMBRAL_TIPOEO = 85


def normalizar(texto: str) -> str:
    """Pasa texto natural a su forma canónica de comparación.

    Minúsculas, sin tildes, sin puntuación y sin espacios repetidos. La ñ
    se conserva porque es una letra propia del español, no un acento.
    """
    if not texto:
        return ""

    # NFKD separa la "ó" en "o" + tilde combinante; al quedarse solo con los
    # caracteres no combinantes, la tilde desaparece y la ñ sobrevive.
    sin_tildes = "".join(
        caracter for caracter in unicodedata.normalize("NFKD", texto.lower())
        if not unicodedata.combining(caracter)
    )
    sin_puntuacion = _CARACTERES_PERMITIDOS.sub(" ", sin_tildes)
    return _ESPACIOS.sub(" ", sin_puntuacion).strip()


def corregir_tipeo(texto: str, vocabulario: set[str], umbral: int = UMBRAL_TIPOEO) -> str:
    """Corrige palabras mal escritas contra un vocabulario conocido.

    Usa la distancia de Levenshtein de rapidfuzz: para cada palabra que no
    exista en el vocabulario se busca la más cercana y, si supera `umbral`
    de similitud, se sustituye.

    Se respetan dos excepciones que evitan metidas de pata:
      - Palabras de 3 letras o menos: la distancia entre dos palabras cortas
        es tan pequeña que casi cualquier corrección sería válida.
      - Números: "200" no es "200 g" mal escrito, es una cantidad.
    """
    from rapidfuzz import fuzz, process

    if not texto:
        return ""

    palabras = texto.split()
    conocidas = set(vocabulario)
    # Se corrige contra lo que ya está bien escrito, no contra el propio
    # texto corregido: así el resultado no depende del orden de las palabras.
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
        # extractOne devuelve una tupla cuya longitud varía entre versiones
        # de rapidfuzz (2 o 3 elementos según incluya indice/clave), así que
        # se lee por posicion en vez de desempaquetar a ciegas.
        coincidencia, puntuacion = mejor[0], mejor[1]
        if puntuacion >= umbral:
            palabras[indice] = coincidencia
            desplazamiento[palabra] = coincidencia

    return " ".join(palabras)
