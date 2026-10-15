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
    """Un pago parcial o total de una orden. Una orden puede tener varios (pago mixto)."""

    PENDIENTE, APROBADO, RECHAZADO, ANULADO = "PENDIENTE", "APROBADO", "RECHAZADO", "ANULADO"
    ESTADO_CHOICES = [
        (PENDIENTE, "Pendiente"),
        (APROBADO, "Aprobado"),
        (RECHAZADO, "Rechazado"),
        (ANULADO, "Anulado"),
    ]

    orden = models.ForeignKey("operativo.Orden", on_delete=models.PROTECT, related_name="pagos")
    metodo_pago = models.ForeignKey(MetodoPago, on_delete=models.PROTECT, related_name="pagos")
    # `monto` abona a la cuenta; la propina va aparte y NO cuenta para el saldo.
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    propina = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=APROBADO)
    referencia_transaccion = models.CharField(max_length=100, blank=True)
    cobrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Datos de la pasarela (vacíos en efectivo/transferencia).
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
    """Cada webhook recibido. La restricción única garantiza la idempotencia:
    el mismo evento nunca se procesa dos veces."""

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
    """Bitácora de cobros: quién, cuándo (creado_en) y cuánto. Solo se agregan filas."""

    COBRO, PASARELA_INICIADA, PASARELA_APROBADA, PASARELA_RECHAZADA, ALERTA = (
        "COBRO", "PASARELA_INICIADA", "PASARELA_APROBADA", "PASARELA_RECHAZADA", "ALERTA",
    )
    ACCION_CHOICES = [
        (COBRO, "Cobro registrado"),
        (PASARELA_INICIADA, "Cobro con tarjeta iniciado"),
        (PASARELA_APROBADA, "Pasarela aprobó el pago"),
        (PASARELA_RECHAZADA, "Pasarela rechazó el pago"),
        (ALERTA, "Alerta (inconsistencia)"),
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
    

# ---------------------------------------------------------------------------
# Cobro por QR (celular del cliente) y comprobante de venta
# ---------------------------------------------------------------------------
import secrets  # noqa: E402
from datetime import timedelta  # noqa: E402

from django.utils import timezone  # noqa: E402


def _nuevo_token():
    return secrets.token_urlsafe(24)


def _vence_en_dos_horas():
    return timezone.now() + timedelta(hours=2)


class EnlacePago(TimestampedModel):
    """Enlace secreto que va dentro del QR. Permite al cliente ver y pagar SOLO su cuenta."""

    orden = models.ForeignKey("operativo.Orden", on_delete=models.PROTECT, related_name="enlaces_pago")
    token = models.CharField(max_length=64, unique=True, default=_nuevo_token)
    expira_en = models.DateTimeField(default=_vence_en_dos_horas)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"QR orden #{self.orden_id}"

    @property
    def vigente(self):
        return timezone.now() < self.expira_en


class Factura(TimestampedModel):
    """Comprobante de venta SIMULADO (sin validez fiscal). Se emite al quedar pagada la orden.
    Guarda una copia de los datos para que no cambie aunque luego cambien precios o clientes."""

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