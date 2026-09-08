from django.db.models import Sum
from django.utils import timezone
from django.views.generic import TemplateView

from caja.models import Pago
from catalogo.models import Producto
from core.mixins import RoleRequiredMixin
from cuentas.models import Usuario
from inventario.models import ItemInventario
from operativo.models import Mesa, Orden

ROLES_ADMIN = ["ADMINISTRADOR"]


class DashboardView(RoleRequiredMixin, TemplateView):
    roles_permitidos = ROLES_ADMIN
    template_name = "reportes/dashboard.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        contexto.update(
            total_usuarios=Usuario.objects.filter(is_active=True).count(),
            total_productos=Producto.objects.count(),
            total_mesas=Mesa.objects.count(),
            mesas_ocupadas=Mesa.objects.filter(estado=Mesa.OCUPADA).count(),
            items_stock_bajo=[i for i in ItemInventario.objects.all() if i.stock_bajo],
            ordenes_hoy=Orden.objects.filter(creado_en__date=hoy).count(),
            ventas_hoy=Pago.objects.filter(creado_en__date=hoy).aggregate(total=Sum("monto"))["total"] or 0,
        )
        return contexto


class ReportesView(RoleRequiredMixin, TemplateView):
    roles_permitidos = ROLES_ADMIN
    template_name = "reportes/reportes.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            ordenes_por_estado={
                estado: Orden.objects.filter(estado=estado).count()
                for estado, _ in Orden.ESTADO_CHOICES
            },
            ventas_por_metodo=(
                Pago.objects.values("metodo_pago__nombre").annotate(total=Sum("monto"))
            ),
        )
        return contexto
