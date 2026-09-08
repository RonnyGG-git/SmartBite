from django.db import models


class TimestampedModel(models.Model):
    """Modelo base abstracto: agrega creado_en/actualizado_en a quien herede de él."""

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
