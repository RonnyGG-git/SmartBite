from django.contrib import admin

from .models import Retroalimentacion


@admin.register(Retroalimentacion)
class RetroalimentacionAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo", "mesa", "revisada", "creado_en")
    list_filter = ("tipo", "revisada")
    search_fields = ("mensaje", "nombre", "contacto")
