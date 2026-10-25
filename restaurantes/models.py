import secrets

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimestampedModel

ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LARGO_CODIGO = 8


def generar_codigo_acceso():
    while True:
        codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(LARGO_CODIGO))
        if not Restaurante.objects.filter(codigo_acceso=codigo).exists():
            return codigo


class Restaurante(TimestampedModel):
    nombre = models.CharField(max_length=150)
    nif = models.CharField("NIF", max_length=30, unique=True)
    email = models.EmailField()
    direccion = models.CharField(max_length=255)
    telefono = models.CharField(max_length=30, blank=True)
    telefono_secundario = models.CharField(max_length=30, blank=True)
    administrador = models.ForeignKey(
        "cuentas.Usuario", on_delete=models.PROTECT, related_name="restaurantes_administrados",
        null=True, blank=True,
    )
    codigo_acceso = models.CharField(max_length=LARGO_CODIGO, unique=True, editable=False)
    logo_url = models.URLField(blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def save(self, *args, **kwargs):
        if not self.codigo_acceso:
            self.codigo_acceso = generar_codigo_acceso()
        super().save(*args, **kwargs)

    def regenerar_codigo_acceso(self):
        self.codigo_acceso = generar_codigo_acceso()
        self.save(update_fields=["codigo_acceso", "actualizado_en"])

    def __str__(self):
        return self.nombre


class Sucursal(TimestampedModel):
    restaurante = models.ForeignKey(Restaurante, on_delete=models.CASCADE, related_name="sucursales")
    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=30, blank=True)
    latitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitud = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def tiene_ubicacion(self):
        return self.latitud is not None and self.longitud is not None
