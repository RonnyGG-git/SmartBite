from django.contrib import admin

from .models import Restaurante, Sucursal


@admin.register(Restaurante)
class RestauranteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nif", "email", "activo")
    search_fields = ("nombre", "nif", "email")


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "restaurante", "activo")
    list_filter = ("restaurante", "activo")
