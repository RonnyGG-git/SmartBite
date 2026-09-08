from django.contrib import admin

from .models import MetodoPago, Pago


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("id", "orden", "metodo_pago", "monto", "creado_en")
    list_filter = ("metodo_pago",)
