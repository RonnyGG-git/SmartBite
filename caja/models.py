from decimal import Decimal

from django.conf import settings
from django.db import models

from core.models import TimestampedModel


class MetodoPago(TimestampedModel):
    nombre = models.CharField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)
    usa_pasarela = models.BooleanField(
        default=False,
        help_text="Si está activo, el cobro se hace a través de la pasarela (tarjeta).",
    )

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    @property
    def requiere_pasarela(self):
        return self.usa_pasarela or self.nombre.strip().lower() == "tarjeta"


class Pago(TimestampedModel):
    PENDIENTE, APROBADO, RECHAZADO, ANULADO = "PENDIENTE", "APROBADO", "RECHAZADO", "ANULADO"
    ESTADO_CHOICES = [
        (PENDIENTE, "Pendiente"),
        (APROBADO, "Aprobado"),
        (RECHAZADO, "Rechazado"),
        (ANULADO, "Anulado"),
    ]

    orden = models.ForeignKey("operativo.Orden", on_delete=models.PROTECT, related_name="pagos")
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name="pagos")
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    propina = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=APROBADO)
    referencia_transaccion = models.CharField(max_length=100, blank=True)
    cobrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    proveedor = models.CharField(max_length=20, blank=True)
    referencia_pasarela = models.CharField(max_length=100, blank=True)
    id_transaccion_pasarela = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(
                fields=["referencia_pasarela"],
                condition=~models.Q(referencia_pasarela=""),
                name="uniq_pago_referencia_pasarela",
            ),
            models.UniqueConstraint(
                fields=["proveedor", "id_transaccion_pasarela"],
                condition=~models.Q(id_transaccion_pasarela=""),
                name="uniq_pago_transaccion_pasarela",
            ),
            models.CheckConstraint(condition=models.Q(monto__gt=0), name="pago_monto_positivo"),
            models.CheckConstraint(condition=models.Q(propina__gte=0), name="pago_propina_no_negativa"),
        ]

    def __str__(self):
        return f"Pago #{self.pk} — Orden #{self.orden_id}"

    @property
    def total_cobrado(self):
        return self.monto + self.propina


class EventoPasarela(TimestampedModel):
    proveedor = models.CharField(max_length=20)
    evento_id = models.CharField(max_length=150)
    payload = models.JSONField(default=dict)
    resultado = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [
            models.UniqueConstraint(fields=["proveedor", "evento_id"], name="uniq_evento_pasarela")
        ]

    def __str__(self):
        return f"{self.proveedor} {self.evento_id}"


class AuditoriaCobro(TimestampedModel):
    COBRO, PASARELA_INICIADA, PASARELA_APROBADA, PASARELA_RECHAZADA, ALERTA = (
        "COBRO", "PASARELA_INICIADA", "PASARELA_APROBADA", "PASARELA_RECHAZADA", "ALERTA",
    )
    EFECTIVO_SOLICITADO = "EFECTIVO_SOLICITADO"
    PAGO_ANULADO = "PAGO_ANULADO"
    ACCION_CHOICES = [
        (COBRO, "Cobro registrado"),
        (PASARELA_INICIADA, "Cobro con tarjeta iniciado"),
        (PASARELA_APROBADA, "Pasarela aprobó el pago"),
        (PASARELA_RECHAZADA, "Pasarela rechazó el pago"),
        (ALERTA, "Alerta (inconsistencia)"),
        (EFECTIVO_SOLICITADO, "El cliente pagará en efectivo"),
        (PAGO_ANULADO, "Intento de pago en línea anulado"),
    ]

    accion = models.CharField(max_length=20, choices=ACCION_CHOICES)
    orden = models.ForeignKey("operativo.Orden", on_delete=models.PROTECT, related_name="+")
    pago = models.ForeignKey(Pago, on_delete=models.PROTECT, null=True, blank=True, related_name="auditorias")
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    monto = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    propina = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    detalle = models.CharField(max_length=255, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.get_accion_display()} — orden #{self.orden_id}"
    

import secrets
from datetime import timedelta

from django.utils import timezone


def _nuevo_token():
    return secrets.token_urlsafe(24)


def _vence_en_dos_horas():
    return timezone.now() + timedelta(hours=2)


class EnlacePago(TimestampedModel):
    orden = models.ForeignKey("operativo.Orden", on_delete=models.PROTECT, related_name="enlaces_pago")
    token = models.CharField(max_length=64, unique=True, default=_nuevo_token)
    expira_en = models.DateTimeField(default=_vence_en_dos_horas)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    efectivo_solicitado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"QR orden #{self.orden_id}"

    @property
    def vigente(self):
        return timezone.now() < self.expira_en


class Factura(TimestampedModel):
    PREFIJO = "SB"

    orden = models.OneToOneField("operativo.Orden", on_delete=models.PROTECT, related_name="factura")
    numero = models.PositiveIntegerField(unique=True)
    cliente_nombre = models.CharField(max_length=150)
    cliente_documento = models.CharField(max_length=30)
    cliente_email = models.EmailField(blank=True)
    base_gravable = models.DecimalField(max_digits=12, decimal_places=2)
    inc = models.DecimalField("Impuesto al consumo", max_digits=12, decimal_places=2)
    total_consumo = models.DecimalField(max_digits=12, decimal_places=2)
    propina = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    total_pagado = models.DecimalField(max_digits=12, decimal_places=2)
    cufe = models.CharField("CUFE (simulado)", max_length=96, blank=True)
    detalle = models.JSONField(default=dict)

    class Meta:
        ordering = ["-numero"]

    def __str__(self):
        return self.codigo

    @property
    def codigo(self):
        return f"{self.PREFIJO}-{self.numero:06d}"