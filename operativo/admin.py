from django.contrib import admin

from .models import Cliente, DetalleOrden, Mesa, Orden, Reserva


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
    list_display = ("id", "mesa", "sucursal", "cliente", "estado", "origen", "creado_en")
    list_filter = ("estado", "origen")
    inlines = [DetalleOrdenInline]


@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "mesa", "fecha_hora", "num_personas", "nombre", "estado")
    list_filter = ("estado", "mesa__sucursal")
    search_fields = ("codigo", "nombre", "telefono")
