"""Buscador de recetas por similitud TF-IDF y filtros explícitos.

Combina dos señales:

  1. Similitud coseno TF-IDF entre la consulta y el texto de cada receta.
     Responde a "¿de qué habla esta receta?".
  2. Bonos fijos por coincidencia exacta de filtros (categoría, dificultad,
     ingredientes, tiempo). Responde a "¿qué pidió exactamente el usuario?".

La similitud manda en el orden de magnitud, pero un filtro explícito gana
por encima: si el usuario dice "postre", ninguna receta salada debe
aparecerle solo porque comparta palabras con la frase.

Todo es determinista y offline: sin LLM, sin red, sin aleatoriedad.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .diccionarios import PESOS, UMBRAL_MINIMO
from .filtros import aplicar_sinonimos, extraer_filtros
from .normalizar import corregir_tipeo, normalizar

# Palabras vacías del español más las del propio dominio ("quiero una
# receta de"): no aportan nada al coseno y solo diluyen la señal.
STOPWORDS = [
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "con", "sin", "para", "por", "y", "o", "que", "del", "al",
    "es", "son", "me", "te", "se", "lo", "le", "su", "sus",
    "quiero", "busco", "necesito", "dame", "tengo", "hay", "receta",
    "recetas", "algo", "plato", "cosa", "comida", "cocina",
]


@dataclass
class Sugerencia:
    """Una receta candidata con por qué fue seleccionada."""

    receta: dict
    puntaje: float
    # Filtros que esta receta cumple de los que pidió el usuario. Es la
    # parte explicable: sin ella el usuario recibe un número y nada más.
    coincidencias: list = field(default_factory=list)
    # Pendiente de la Fase 3: lo rellena el cruce con el inventario real.
    inventario: list = field(default_factory=list)


class Buscador:
    """Indexa un conjunto de recetas y las consulta en lenguaje natural."""

    def __init__(self, recetas: list[dict]):
        self.recetas = recetas
        self.ingredientes_conocidos = {
            str(ingrediente)
            for receta in recetas
            for ingrediente in (receta.get("ingredientes") or [])
        }
        # ngram_range=(1,2): los bigramas son los que hacen que "arroz con
        # pollo" puntúe alto frente a una receta con las mismas palabras
        # sueltas pero en otro orden.
        self.vectorizador = TfidfVectorizer(
            stop_words=STOPWORDS, ngram_range=(1, 2), sublinear_tf=True
        )
        textos = [receta.get("texto_busqueda") or "" for receta in recetas]
        # Sin recetas (instalación recién hecha) o con todas vacías, el
        # vectorizador aborta con "empty vocabulary". En vez de fingir un
        # documento, se deja la matriz sin indexar y buscar() devuelve vacío.
        self.matriz = (
            self.vectorizador.fit_transform(textos)
            if any(texto.strip() for texto in textos)
            else None
        )

    def buscar(self, consulta: str, top: int = 3) -> dict:
        """Devuelve sugerencias para una consulta en lenguaje natural."""
        texto = normalizar(consulta)
        texto = aplicar_sinonimos(texto)
        # El vocabulario del corrector son las palabras de las recetas, que
        # es contra lo que tiene sentido "acercar" lo que escribió el
        # usuario.
        vocabulario = set(self.ingredientes_conocidos)
        vocabulario.update(
            palabra
            for receta in recetas_texto(self.recetas)
            for palabra in receta.split()
        )
        texto = corregir_tipeo(texto, vocabulario)

        filtros = extraer_filtros(texto, self.ingredientes_conocidos)

        if texto.strip() and self.matriz is not None:
            similitudes = cosine_similarity(
                self.vectorizador.transform([texto]), self.matriz
            )[0]
        else:
            similitudes = [0.0] * len(self.recetas)

        sugerencias: list[Sugerencia] = []
        for indice, receta in enumerate(self.recetas):
            puntaje = float(similitudes[indice]) * PESOS["similitud"]
            puntaje += self._bonos(receta, filtros)
            sugerencias.append(
                Sugerencia(
                    receta=receta,
                    puntaje=round(puntaje, 4),
                    coincidencias=self._coincidencias(receta, filtros),
                )
            )

        sugerencias.sort(key=lambda sugerencia: sugerencia.puntaje, reverse=True)

        buenos = [s for s in sugerencias if s.puntaje >= UMBRAL_MINIMO][:top]
        # Expresión única, sin rama: si nadie pasó el umbral pero sí se pidió
        # una categoría, se ofrecen las más parecidas dentro de ella, para que
        # el usuario reciba una alternativa y no un "no hay recetas".
        cercanas = [
            s
            for s in sugerencias
            if not buenos
            and filtros["categoria"]
            and s.receta.get("categoria") == filtros["categoria"]
        ][:top]

        return {
            "filtros": filtros,
            "texto_procesado": texto,
            "sugerencias": buenos,
            "cercanas": cercanas,
        }

    def _bonos(self, receta: dict, filtros: dict) -> float:
        """Suma los PESOS de cada filtro que la receta cumple."""
        puntos = 0.0
        if filtros["categoria"] and receta.get("categoria") == filtros["categoria"]:
            puntos += PESOS["categoria"]
        if filtros["dificultad"] and receta.get("dificultad") == filtros["dificultad"]:
            puntos += PESOS["dificultad"]
        tiempo_max = filtros["tiempo_max"]
        if tiempo_max and receta.get("tiempo_min") is not None and receta["tiempo_min"] <= tiempo_max:
            puntos += PESOS["tiempo"]
        if filtros["ingredientes"]:
            ingredientes = {str(i) for i in (receta.get("ingredientes") or [])}
            if ingredientes.intersection(filtros["ingredientes"]):
                puntos += PESOS["ingredientes"]
        return puntos

    def _coincidencias(self, receta: dict, filtros: dict) -> list[str]:
        """Explica en español por qué salió cada receta.

        El usuario no debe recibir un puntaje desnudo: con el motivo puede
        entender por qué el sistema le propose eso.
        """
        motivos: list[str] = []
        if filtros["categoria"] and receta.get("categoria") == filtros["categoria"]:
            motivos.append(f"categoría: {receta.get('categoria')}")
        if filtros["dificultad"] and receta.get("dificultad") == filtros["dificultad"]:
            motivos.append(f"dificultad: {receta.get('dificultad')}")
        tiempo_max = filtros["tiempo_max"]
        if tiempo_max and receta.get("tiempo_min") is not None and receta["tiempo_min"] <= tiempo_max:
            motivos.append(f"tarda {receta['tiempo_min']} min (pediste {tiempo_max})")
        if filtros["ingredientes"]:
            ingredientes = {str(i) for i in (receta.get("ingredientes") or [])}
            comunes = ingredientes.intersection(filtros["ingredientes"])
            if comunes:
                motivos.append(f"usa: {', '.join(sorted(comunes))}")
        return motivos


def recetas_texto(recetas: list[dict]) -> list[str]:
    """Textos de búsqueda de las recetas, sin entradas vacías."""
    return [receta.get("texto_busqueda") or "" for receta in recetas]
