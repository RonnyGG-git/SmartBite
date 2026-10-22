import sys
from pathlib import Path

LIB = Path(r"C:\Users\elhac\OneDrive\Documentos\MiCerebro\skills\diagramas-uml\scripts")
sys.path.insert(0, str(LIB))

DESTINO = Path(__file__).resolve().parent.parent


def salida(nombre):
    return DESTINO / f"{nombre}.drawio", DESTINO / f"{nombre}.png"
