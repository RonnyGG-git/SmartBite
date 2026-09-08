from django.contrib import admin

from .models import Cliente, DetalleOrden, Mesa, Orden


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ("numero", "sucursal", "capacidad", "estado", "activa")
    list_filter = ("sucursal", "estado", "activa")


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "telefono", "email")
    search_fields = ("nombre", "telefono", "numero_documento")


class DetalleOrdenInline(admin.TabularInline):
    model = DetalleOrden
    extra = 0


@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ("id", "mesa", "cliente", "estado", "creado_en")
    list_filter = ("estado",)
    inlines = [DetalleOrdenInline]
