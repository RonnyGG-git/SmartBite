from django.contrib import admin

from .models import Compra, DetalleCompra, ItemInventario, MovimientoInventario, Proveedor


@admin.register(ItemInventario)
class ItemInventarioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sucursal", "stock_actual", "stock_minimo", "unidad_medida")
    list_filter = ("sucursal", "unidad_medida")
    search_fields = ("nombre",)


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ("item", "tipo", "cantidad", "motivo", "creado_en")
    list_filter = ("tipo",)


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "contacto", "telefono", "activo")
    search_fields = ("nombre",)


class DetalleCompraInline(admin.TabularInline):
    model = DetalleCompra
    extra = 1


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = ("id", "proveedor", "estado", "creado_en")
    list_filter = ("estado", "proveedor")
    inlines = [DetalleCompraInline]
