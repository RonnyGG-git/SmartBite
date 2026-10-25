from django.contrib import admin

from .models import LineaTelefonica, Llamada, TurnoLlamada


@admin.register(LineaTelefonica)
class LineaTelefonicaAdmin(admin.ModelAdmin):
    list_display = ("numero", "sucursal", "activa")
    list_filter = ("activa",)


class TurnoLlamadaInline(admin.TabularInline):
    model = TurnoLlamada
    extra = 0
    readonly_fields = ("rol", "texto", "creado_en")


@admin.register(Llamada)
class LlamadaAdmin(admin.ModelAdmin):
    list_display = ("identificador", "canal", "sucursal", "estado", "fase", "orden", "creado_en")
    list_filter = ("canal", "estado")
    inlines = [TurnoLlamadaInline]
