from django.db import models

from core.models import TimestampedModel


class Retroalimentacion(TimestampedModel):
    """CU-PED-17 Enviar retroalimentación. Sugerencia (CU-PED-18) y denuncia
    (CU-PED-19) son sus dos especializaciones; el Administrador las revisa
    en CU-ADM-16."""

    SUGERENCIA = "SUGERENCIA"
    DENUNCIA = "DENUNCIA"
    TIPO_CHOICES = [(SUGERENCIA, "Sugerencia"), (DENUNCIA, "Denuncia")]

    tipo = models.CharField(max_length=12, choices=TIPO_CHOICES, default=SUGERENCIA)
    mensaje = models.TextField(max_length=1000)
    nombre = models.CharField(max_length=150, blank=True)
    contacto = models.CharField(max_length=150, blank=True, help_text="Email o teléfono, si quiere respuesta.")
    mesa = models.ForeignKey(
        "operativo.Mesa", on_delete=models.SET_NULL, null=True, blank=True, related_name="retroalimentaciones"
    )
    revisada = models.BooleanField(default=False)

    class Meta:
        ordering = ["revisada", "-creado_en"]
        verbose_name = "retroalimentación"
        verbose_name_plural = "retroalimentaciones"

    def __str__(self):
        return f"{self.get_tipo_display()} #{self.pk}"
