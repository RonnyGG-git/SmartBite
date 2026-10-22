import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from . import servicio
from .management.commands.cargar_recetas import ARCHIVO_RECETAS
from .models import RecetaSugerida


def _datos_recetas():
    return json.loads(ARCHIVO_RECETAS.read_text(encoding="utf-8"))


class DatosRecetasTests(TestCase):
    """El archivo versionado cumple el contrato que espera el motor."""

    def test_cubre_todas_las_categorias_y_dificultades(self):
        recetas = _datos_recetas()
        self.assertGreaterEqual(len(recetas), 20)
        categorias = {codigo for codigo, _ in RecetaSugerida.CATEGORIA_CHOICES}
        dificultades = {codigo for codigo, _ in RecetaSugerida.DIFICULTAD_CHOICES}
        self.assertEqual({r["categoria"] for r in recetas}, categorias)
        self.assertEqual({r["dificultad"] for r in recetas}, dificultades)

    def test_formato_de_cada_receta(self):
        nombres = set()
        for receta in _datos_recetas():
            with self.subTest(receta=receta["nombre"]):
                self.assertNotIn(receta["nombre"], nombres)
                nombres.add(receta["nombre"])
                self.assertLessEqual(len(receta["descripcion"]), 255)
                self.assertGreater(receta["tiempo_min"], 0)
                self.assertTrue(receta["ingredientes"])
                for ingrediente in receta["ingredientes"]:
                    self.assertIsInstance(ingrediente["nombre"], str)
                    self.assertIsInstance(ingrediente["cantidad"], str)
                self.assertTrue(receta["pasos"])
                self.assertTrue(all(isinstance(paso, str) and paso for paso in receta["pasos"]))


class CargarRecetasTests(TestCase):

    def setUp(self):
        # La caché del buscador es del proceso: sin limpiarla, un test vería
        # el índice construido por otro.
        servicio._cache.update({"firma": None, "buscador": None})

    def _cargar(self):
        call_command("cargar_recetas", stdout=StringIO())

    def test_carga_todas_las_recetas(self):
        self._cargar()
        self.assertEqual(RecetaSugerida.objects.count(), len(_datos_recetas()))

    def test_es_idempotente(self):
        self._cargar()
        total = RecetaSugerida.objects.count()
        self._cargar()
        self.assertEqual(RecetaSugerida.objects.count(), total)

    def test_actualiza_una_receta_existente(self):
        RecetaSugerida.objects.create(
            nombre="Tres leches", descripcion="vieja", categoria=RecetaSugerida.ENTRADA,
            dificultad=RecetaSugerida.DIFICIL, tiempo_min=1,
        )
        self._cargar()
        receta = RecetaSugerida.objects.get(nombre="Tres leches")
        self.assertEqual(receta.categoria, RecetaSugerida.POSTRE)
        self.assertEqual(RecetaSugerida.objects.count(), len(_datos_recetas()))

    def test_consulta_con_resultados(self):
        self._cargar()
        resultado = servicio.consultar("algo dulce y fácil de hacer")
        self.assertTrue(resultado["consultable"])
        self.assertTrue(resultado["sugerencias"])
        self.assertTrue(any(s.receta["categoria"] == RecetaSugerida.POSTRE
                            for s in resultado["sugerencias"]))
