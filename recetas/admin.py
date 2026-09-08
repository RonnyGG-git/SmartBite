from django.contrib import admin

from .models import ProductoIngrediente


@admin.register(ProductoIngrediente)
class ProductoIngredienteAdmin(admin.ModelAdmin):
    list_display = ("producto", "item_inventario", "cantidad_requerida", "activo")
    list_filter = ("activo",)
