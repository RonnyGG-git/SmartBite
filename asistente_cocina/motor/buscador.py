from __future__ import annotations

from dataclasses import dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .diccionarios import PESOS, UMBRAL_MINIMO
from .filtros import aplicar_sinonimos, extraer_filtros
from .normalizar import corregir_tipeo, normalizar

STOPWORDS = [
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas",
    "con", "sin", "para", "por", "y", "o", "que", "del", "al",
    "es", "son", "me", "te", "se", "lo", "le", "su", "sus",
    "quiero", "busco", "necesito", "dame", "tengo", "hay", "receta",
    "recetas", "algo", "plato", "cosa", "comida", "cocina",
]


@dataclass
class Sugerencia:
    receta: dict
    puntaje: float
    coincidencias: list = field(default_factory=list)
    inventario: list = field(default_factory=list)


class Buscador:
    def __init__(self, recetas: list[dict]):
        self.recetas = recetas
        self.ingredientes_conocidos = {
            str(ingrediente)
            for receta in recetas
            for ingrediente in (receta.get("ingredientes") or [])
        }
        self.vectorizador = TfidfVectorizer(
            stop_words=STOPWORDS, ngram_range=(1, 2), sublinear_tf=True
        )
        textos = [receta.get("texto_busqueda") or "" for receta in recetas]
        self.matriz = (
            self.vectorizador.fit_transform(textos)
            if any(texto.strip() for texto in textos)
            else None
        )

    def buscar(self, consulta: str, top: int = 3) -> dict:
        texto = normalizar(consulta)
        texto = aplicar_sinonimos(texto)
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
    return [receta.get("texto_busqueda") or "" for receta in recetas]
