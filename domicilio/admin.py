from django.contrib import admin

from .models import DireccionCliente, Domicilio, PerfilCliente


class DireccionInline(admin.TabularInline):
    model = DireccionCliente
    extra = 0


@admin.register(PerfilCliente)
class PerfilClienteAdmin(admin.ModelAdmin):
    list_display = ("usuario", "telefono", "documento")
    search_fields = ("usuario__email", "usuario__nombre", "telefono", "documento")


@admin.register(DireccionCliente)
class DireccionClienteAdmin(admin.ModelAdmin):
    list_display = ("usuario", "etiqueta", "direccion", "principal")
    search_fields = ("usuario__email", "direccion")


@admin.register(Domicilio)
class DomicilioAdmin(admin.ModelAdmin):
    list_display = ("orden", "cliente", "domiciliario", "estado", "creado_en")
    list_filter = ("estado",)
    search_fields = ("cliente__email", "domiciliario__email", "direccion")
    readonly_fields = ("orden", "codigo_entrega", "intentos_codigo", "lat_actual", "lng_actual", "ubicacion_en")
