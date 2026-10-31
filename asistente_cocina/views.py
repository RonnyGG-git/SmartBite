from django.urls import reverse_lazy
from django.views.generic.edit import FormView

from core.mixins import RoleRequiredMixin

from .forms import ConsultaForm
from .models import ConsultaAsistente
from .servicio import consultar

ROLES_ASISTENTE = ["ADMINISTRADOR", "JEFE_COCINA"]


class AsistenteView(RoleRequiredMixin, FormView):
    roles_permitidos = ROLES_ASISTENTE
    form_class = ConsultaForm
    template_name = "asistente_cocina/asistente.html"
    extra_context = {"titulo": "Asistente de recetas"}
    success_url = reverse_lazy("asistente_cocina:asistente")

    def form_valid(self, form):
        texto = form.cleaned_data["texto"]
        sucursal_id = getattr(self.request.user, "sucursal_id", None)

        resultado = consultar(texto, sucursal_id)

        ConsultaAsistente.objects.create(
            usuario=self.request.user,
            texto=texto,
            filtros_detectados=resultado["filtros"],
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
