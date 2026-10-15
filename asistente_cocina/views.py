"""Vistas del Asistente de Recomendación de Recetas."""

from django.urls import reverse_lazy
from django.views.generic.edit import FormView

from core.mixins import RoleRequiredMixin

from .forms import ConsultaForm
from .models import ConsultaAsistente
from .servicio import consultar

# El asistente propone recetas: lo consultan quienes deciden qué se cocina.
ROLES_ASISTENTE = ["ADMINISTRADOR", "JEFE_COCINA"]


class AsistenteView(RoleRequiredMixin, FormView):
    """Formulario de consulta y resultados.

    Cada búsqueda queda en la bitácora antes de responder: es lo único que
    permitirá medir después si las recomendaciones sirvieron.
    """

    roles_permitidos = ROLES_ASISTENTE
    form_class = ConsultaForm
    template_name = "asistente_cocina/asistente.html"
    extra_context = {"titulo": "Asistente de recetas"}
    success_url = reverse_lazy("asistente_cocina:asistente")

    def form_valid(self, form):
        texto = form.cleaned_data["texto"]
        # La sucursal del usuario es la despensa contra la que se compara.
        # Sin ella el servicio omite el cruce de inventario.
        sucursal_id = getattr(self.request.user, "sucursal_id", None)

        resultado = consultar(texto, sucursal_id)

        ConsultaAsistente.objects.create(
            usuario=self.request.user,
            texto=texto,
            filtros_detectados=resultado["filtros"],
            # Solo el id y el puntaje: guardar la receta entera duplicaría en
            # cada fila de la bitácora lo que ya vive en RecetaSugerida, y
            # además se quedaría congelada aunque la receta cambiara después.
            resultados=[
                {
                    "receta_id": sugerencia.receta.get("id"),
                    "nombre": sugerencia.receta.get("nombre"),
                    "puntaje": sugerencia.puntaje,
                    "coincidencias": sugerencia.coincidencias,
                }
                for sugerencia in resultado["sugerencias"]
            ],
        )

        return self.render_to_response(self.get_context_data(
            form=form, resultado=resultado
        ))
