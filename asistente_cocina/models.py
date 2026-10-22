from django.db import models

from core.models import TimestampedModel


class RecetaSugerida(TimestampedModel):
    ENTRADA = "ENTRADA"
    PLATO_FUERTE = "PLATO_FUERTE"
    POSTRE = "POSTRE"
    BEBIDA = "BEBIDA"
    ACOMPANANTE = "ACOMPANANTE"
    CATEGORIA_CHOICES = [
        (ENTRADA, "Entrada"),
        (PLATO_FUERTE, "Plato fuerte"),
        (POSTRE, "Postre"),
        (BEBIDA, "Bebida"),
        (ACOMPANANTE, "Acompañante"),
    ]

    FACIL = "FACIL"
    MEDIA = "MEDIA"
    DIFICIL = "DIFICIL"
    DIFICULTAD_CHOICES = [
        (FACIL, "Fácil"),
        (MEDIA, "Media"),
        (DIFICIL, "Difícil"),
    ]

    nombre = models.CharField(max_length=150, unique=True)
    descripcion = models.CharField(max_length=255)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    dificultad = models.CharField(max_length=10, choices=DIFICULTAD_CHOICES)
    tiempo_min = models.PositiveIntegerField()
    porciones = models.PositiveIntegerField(default=4)
    ingredientes = models.JSONField(default=list)
    pasos = models.JSONField(default=list)
    etiquetas = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    CATEGORIA_TERMINOS = {
        ENTRADA: "entrada",
        PLATO_FUERTE: "plato principal",
        POSTRE: "postre",
        BEBIDA: "bebida",
        ACOMPANANTE: "acompanamiento",
    }

    def texto_busqueda(self) -> str:
        from .motor.normalizar import normalizar

        partes = [self.nombre, self.descripcion, self.etiquetas]
        partes.append(self.CATEGORIA_TERMINOS.get(self.categoria, self.categoria.lower()))
        for ingrediente in self.ingredientes or []:
            if isinstance(ingrediente, dict):
                partes.append(str(ingrediente.get("nombre", "")))
            else:
                partes.append(str(ingrediente))
        return normalizar(" ".join(parte for parte in partes if parte))


class ConsultaAsistente(TimestampedModel):
    usuario = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultas_asistente",
    )
    texto = models.CharField(max_length=300)
    filtros_detectados = models.JSONField(default=dict)
    resultados = models.JSONField(default=list)
    util = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return self.texto[:60]
