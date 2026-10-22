import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from asistente_cocina.models import RecetaSugerida

# El archivo vive junto a la app para que la base de conocimiento quede
# versionada con el código. No es un fixture de loaddata (no lleva model/pk):
# se carga por nombre para que el comando sea idempotente.
ARCHIVO_RECETAS = Path(__file__).resolve().parents[2] / "fixtures" / "recetas.json"

CAMPOS = ("descripcion", "categoria", "dificultad", "tiempo_min", "porciones",
          "ingredientes", "pasos", "etiquetas", "activo")


class Command(BaseCommand):
    help = ("Carga (o actualiza) las recetas de la base de conocimiento del asistente. "
            "Es idempotente: identifica cada receta por su nombre.")

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            default=str(ARCHIVO_RECETAS),
            help="Ruta del JSON con las recetas (por defecto asistente_cocina/fixtures/recetas.json).",
        )

    def handle(self, *args, **options):
        ruta = Path(options["archivo"])
        try:
            recetas = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CommandError(f"No se pudo leer {ruta}: {error}")

        creadas = actualizadas = 0
        # Todo o nada: una receta inválida no deja la base a medias.
        with transaction.atomic():
            for datos in recetas:
                nombre = datos.get("nombre")
                receta = RecetaSugerida.objects.filter(nombre=nombre).first()
                es_nueva = receta is None
                if es_nueva:
                    receta = RecetaSugerida(nombre=nombre)
                for campo in CAMPOS:
                    if campo in datos:
                        setattr(receta, campo, datos[campo])
                try:
                    receta.full_clean()
                except ValidationError as error:
                    raise CommandError(f"Receta inválida '{nombre}': {error.message_dict}")
                receta.save()
                if es_nueva:
                    creadas += 1
                    self.stdout.write(self.style.SUCCESS(f"Receta creada: {nombre}"))
                else:
                    actualizadas += 1

        self.stdout.write(self.style.SUCCESS(
            f"Recetas listas: {creadas} creadas, {actualizadas} actualizadas."
        ))
