from django.contrib import admin

from .models import ConsultaAsistente, RecetaSugerida


@admin.register(RecetaSugerida)
class RecetaSugeridaAdmin(admin.ModelAdmin):
    """Alta y edición de la base de conocimiento del asistente."""

    list_display = ["nombre", "categoria", "dificultad", "tiempo_min", "activo"]
    list_filter = ["categoria", "dificultad", "activo"]
    search_fields = ["nombre", "descripcion", "etiquetas"]
    list_editable = ["activo"]
    ordering = ["nombre"]


@admin.register(ConsultaAsistente)
class ConsultaAsistenteAdmin(admin.ModelAdmin):
    """Bitácora de consultas, solo lectura.

    Es un registro de auditoría, no un formulario: los datos los escribe el
    asistente al responder, no un administrador. Dejarlo editable invite a
    falsear justo la información que sirve para medir la calidad.
    """

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
        # Borrar un registro de auditoría también sería falsearlo, así que
        # tampoco se deja. Negarlo en el permiso (y no en el botón) es lo que
        # impide saltárselo llamando a la URL directamente.
        return False
