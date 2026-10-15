from django.contrib import admin

from .models import AuditoriaCobro, EventoPasarela, MetodoPago, Pago


@admin.register(MetodoPago)
class MetodoPagoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "usa_pasarela")


@admin.register(Pago)
class PagoAdmin(admin.ModelAdmin):
    list_display = ("id", "orden", "metodo_pago", "monto", "propina", "estado", "cobrado_por", "creado_en")
    list_filter = ("estado", "metodo_pago", "proveedor")


class SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditoriaCobro)
class AuditoriaCobroAdmin(SoloLectura):
    list_display = ("creado_en", "accion", "orden", "usuario", "monto", "propina", "ip")
    list_filter = ("accion",)


@admin.register(EventoPasarela)
class EventoPasarelaAdmin(SoloLectura):
    list_display = ("creado_en", "proveedor", "evento_id", "resultado")