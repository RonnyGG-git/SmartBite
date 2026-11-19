from django.db import models

from core.models import TimestampedModel


class LineaTelefonica(TimestampedModel):
    numero = models.CharField(max_length=20, unique=True)
    sucursal = models.ForeignKey("restaurantes.Sucursal", on_delete=models.PROTECT, related_name="lineas_telefonicas")
    activa = models.BooleanField(default=True)
    numero_transferencia = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["numero"]
        verbose_name = "línea telefónica"
        verbose_name_plural = "líneas telefónicas"

    def __str__(self):
        return f"{self.numero} → {self.sucursal}"


class Llamada(TimestampedModel):
    CANAL_TELEFONO, CANAL_WHATSAPP, CANAL_DEMO = "TELEFONO", "WHATSAPP", "DEMO"
    CANAL_CHOICES = [(CANAL_TELEFONO, "Teléfono"), (CANAL_WHATSAPP, "WhatsApp"), (CANAL_DEMO, "Simulador")]

    ACTIVA, FINALIZADA, CORTADA, TRANSFERIDA, FALLIDA = "ACTIVA", "FINALIZADA", "CORTADA", "TRANSFERIDA", "FALLIDA"
    ESTADO_CHOICES = [
        (ACTIVA, "Activa"),
        (FINALIZADA, "Finalizada"),
        (CORTADA, "Cortada por el cliente"),
        (TRANSFERIDA, "Transferida a un operador"),
        (FALLIDA, "Fallida"),
    ]

    FASE_PEDIDO = "PEDIDO"
    FASE_DATOS_REGISTRADOS = "DATOS_REGISTRADOS"
    FASE_NOMBRE = "NOMBRE"
    FASE_TELEFONO = "TELEFONO"
    FASE_MODALIDAD = "MODALIDAD"
    FASE_DIRECCION = "DIRECCION"
    FASE_REFERENCIA = "REFERENCIA"
    FASE_CONFIRMACION = "CONFIRMACION"
    FASE_RESERVA_FECHA = "RESERVA_FECHA"
    FASE_RESERVA_HORA = "RESERVA_HORA"
    FASE_RESERVA_PERSONAS = "RESERVA_PERSONAS"
    FASE_RESERVA_NOMBRE = "RESERVA_NOMBRE"
    FASE_RESERVA_TELEFONO = "RESERVA_TELEFONO"
    FASE_RESERVA_CONFIRMACION = "RESERVA_CONFIRMACION"
    FASES_RESERVA = (
        FASE_RESERVA_FECHA, FASE_RESERVA_HORA, FASE_RESERVA_PERSONAS, FASE_RESERVA_NOMBRE, FASE_RESERVA_TELEFONO,
        FASE_RESERVA_CONFIRMACION,
    )
    FASE_CERRADA = "CERRADA"
    FASE_CHOICES = [
        (FASE_PEDIDO, "Tomando pedido"),
        (FASE_DATOS_REGISTRADOS, "Confirmando datos registrados"),
        (FASE_NOMBRE, "Pidiendo nombre"),
        (FASE_TELEFONO, "Pidiendo teléfono"),
        (FASE_MODALIDAD, "Pidiendo modalidad"),
        (FASE_DIRECCION, "Pidiendo dirección"),
        (FASE_REFERENCIA, "Pidiendo referencia"),
        (FASE_CONFIRMACION, "Confirmando pedido"),
        (FASE_RESERVA_FECHA, "Reserva: fecha"),
        (FASE_RESERVA_HORA, "Reserva: hora"),
        (FASE_RESERVA_PERSONAS, "Reserva: personas"),
        (FASE_RESERVA_NOMBRE, "Reserva: nombre"),
        (FASE_RESERVA_TELEFONO, "Reserva: teléfono"),
        (FASE_RESERVA_CONFIRMACION, "Reserva: confirmación"),
        (FASE_CERRADA, "Cerrada"),
    ]

    identificador = models.CharField(max_length=64, unique=True)
    canal = models.CharField(max_length=10, choices=CANAL_CHOICES, default=CANAL_TELEFONO)
    linea = models.ForeignKey(LineaTelefonica, on_delete=models.SET_NULL, null=True, blank=True, related_name="llamadas")
    sucursal = models.ForeignKey("restaurantes.Sucursal", on_delete=models.PROTECT, related_name="llamadas")
    telefono_origen = models.CharField(max_length=20, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADO_CHOICES, default=ACTIVA)
    fase = models.CharField(max_length=20, choices=FASE_CHOICES, default=FASE_PEDIDO)
    items = models.JSONField(default=dict, blank=True)
    pendiente = models.JSONField(default=dict, blank=True)
    observaciones = models.CharField(max_length=300, blank=True)
    nombre_cliente = models.CharField(max_length=150, blank=True)
    telefono_contacto = models.CharField(max_length=20, blank=True)
    tipo_consumo = models.CharField(max_length=15, blank=True)
    cliente = models.ForeignKey("operativo.Cliente", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    datos_registrados_ofrecidos = models.BooleanField(default=False)
    resumen_leido = models.BooleanField(default=False)
    silencios = models.PositiveSmallIntegerField(default=0)
    orden = models.OneToOneField(
        "operativo.Orden", on_delete=models.SET_NULL, null=True, blank=True, related_name="llamada_telefonica"
    )
    reserva = models.OneToOneField(
        "operativo.Reserva", on_delete=models.SET_NULL, null=True, blank=True, related_name="llamada_telefonica"
    )
    datos = models.JSONField(default=dict, blank=True)
    direccion = models.CharField(max_length=255, blank=True)
    referencia = models.CharField(max_length=255, blank=True)
    latitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitud = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    ultimo_mensaje = models.CharField(max_length=64, blank=True)
    finalizada_en = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"Llamada {self.identificador}"

    @property
    def abierta(self):
        return self.estado == self.ACTIVA


class TurnoLlamada(models.Model):
    CLIENTE, AGENTE = "CLIENTE", "AGENTE"
    ROL_CHOICES = [(CLIENTE, "Cliente"), (AGENTE, "Agente")]

    llamada = models.ForeignKey(Llamada, on_delete=models.CASCADE, related_name="turnos")
    rol = models.CharField(max_length=8, choices=ROL_CHOICES)
    texto = models.TextField(max_length=2000)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en", "pk"]
