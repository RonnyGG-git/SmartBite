from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimestampedModel

LATITUD = [MinValueValidator(-90), MaxValueValidator(90)]
LONGITUD = [MinValueValidator(-180), MaxValueValidator(180)]


class PerfilCliente(TimestampedModel):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil_cliente")
    telefono = models.CharField(max_length=30, blank=True)
    documento = models.CharField(max_length=30, blank=True)

    class Meta:
        verbose_name = "perfil de cliente"
        verbose_name_plural = "perfiles de cliente"

    def __str__(self):
        return f"Perfil de {self.usuario}"


class DireccionCliente(TimestampedModel):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="direcciones")
    etiqueta = models.CharField(max_length=40, default="Casa")
    direccion = models.CharField(max_length=255)
    referencia = models.CharField(max_length=255, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, validators=LATITUD)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, validators=LONGITUD)
    principal = models.BooleanField(default=False)

    class Meta:
        ordering = ["-principal", "etiqueta"]
        verbose_name = "dirección de cliente"
        verbose_name_plural = "direcciones de cliente"

    def __str__(self):
        return f"{self.etiqueta}: {self.direccion}"


class Domicilio(TimestampedModel):
    SOLICITADO = "SOLICITADO"
    CONFIRMADO = "CONFIRMADO"
    EN_COCINA = "EN_COCINA"
    LISTO_PARA_RECOGER = "LISTO_PARA_RECOGER"
    ASIGNADO = "ASIGNADO"
    EN_CAMINO = "EN_CAMINO"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"
    ESTADO_CHOICES = [
        (SOLICITADO, "Solicitado"),
        (CONFIRMADO, "Confirmado por el restaurante"),
        (EN_COCINA, "En cocina"),
        (LISTO_PARA_RECOGER, "Listo para recoger"),
        (ASIGNADO, "Domiciliario asignado"),
        (EN_CAMINO, "En camino"),
        (ENTREGADO, "Entregado"),
        (CANCELADO, "Cancelado"),
    ]
    FINALES = (ENTREGADO, CANCELADO)
    EN_RUTA = (ASIGNADO, EN_CAMINO)
    MAX_INTENTOS_CODIGO = 5

    orden = models.OneToOneField("operativo.Orden", on_delete=models.CASCADE, related_name="domicilio")
    cliente = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="domicilios_pedidos")
    domiciliario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="domicilios_entregados", null=True, blank=True
    )
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=SOLICITADO)
    direccion = models.CharField(max_length=255)
    referencia = models.CharField(max_length=255, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, validators=LATITUD)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, validators=LONGITUD)
    telefono = models.CharField(max_length=30, blank=True)
    codigo_entrega = models.CharField(max_length=4)
    intentos_codigo = models.PositiveSmallIntegerField(default=0)
    lat_actual = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=LATITUD)
    lng_actual = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=LONGITUD)
    ubicacion_en = models.DateTimeField(null=True, blank=True)
    asignado_en = models.DateTimeField(null=True, blank=True)
    recogido_en = models.DateTimeField(null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        indexes = [models.Index(fields=["estado", "domiciliario"])]

    def __str__(self):
        return f"Domicilio de la orden #{self.orden_id}"

    @property
    def es_final(self):
        return self.estado in self.FINALES

    @property
    def codigo_bloqueado(self):
        return self.intentos_codigo >= self.MAX_INTENTOS_CODIGO
