from django.contrib import admin

from .models import ConsultaAsistente, RecetaSugerida


@admin.register(RecetaSugerida)
class RecetaSugeridaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "categoria", "dificultad", "tiempo_min", "activo"]
    list_filter = ["categoria", "dificultad", "activo"]
    search_fields = ["nombre", "descripcion", "etiquetas"]
    list_editable = ["activo"]
    ordering = ["nombre"]


@admin.register(ConsultaAsistente)
class ConsultaAsistenteAdmin(admin.ModelAdmin):
    list_display = ["texto", "usuario", "creado_en", "util"]
    list_filter = ["util", "creado_en"]
    search_fields = ["texto", "usuario__email"]
    date_hierarchy = "creado_en"
    readonly_fields = [
        "creado_en", "actualizado_en", "usuario", "texto",
        "filtros_detectados", "resultados", "util",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
