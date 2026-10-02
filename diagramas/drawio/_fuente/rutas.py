"""Rutas compartidas por los scripts que generan los diagramas de Inventario.

La librería de formas vive en la skill diagramas-uml de MiCerebro (una sola
copia para todos los proyectos)."""
import sys
from pathlib import Path

LIB = Path(r"C:\Users\elhac\OneDrive\Documentos\MiCerebro\skills\diagramas-uml\scripts")
sys.path.insert(0, str(LIB))

DESTINO = Path(__file__).resolve().parent.parent


def salida(nombre):
    return DESTINO / f"{nombre}.drawio", DESTINO / f"{nombre}.png"
