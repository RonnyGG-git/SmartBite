from django.db.models import Sum
from django.utils import timezone
from django.views.generic import TemplateView

from caja.models import Pago
from catalogo.models import Producto
from core.mixins import RoleRequiredMixin
from core.tenancy import filtrar
from cuentas.views import usuarios_del_restaurante
from inventario.models import ItemInventario
from operativo.models import Mesa, Orden

ROLES_ADMIN = ["ADMINISTRADOR"]


class DashboardView(RoleRequiredMixin, TemplateView):
    roles_permitidos = ROLES_ADMIN
    template_name = "reportes/dashboard.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        mesas = filtrar(Mesa.objects, self.request, "sucursal__restaurante")
        ordenes = filtrar(Orden.objects, self.request, "mesa__sucursal__restaurante")
        pagos = filtrar(Pago.objects, self.request, "orden__mesa__sucursal__restaurante")
        items = filtrar(ItemInventario.objects, self.request, "sucursal__restaurante")
        contexto.update(
            total_usuarios=usuarios_del_restaurante(self.request).filter(is_active=True).count(),
            total_productos=filtrar(Producto.objects, self.request, "sucursal__restaurante").count(),
            total_mesas=mesas.count(),
            mesas_ocupadas=mesas.filter(estado=Mesa.OCUPADA).count(),
            items_stock_bajo=[i for i in items if i.stock_bajo],
            ordenes_hoy=ordenes.filter(creado_en__date=hoy).count(),
            ventas_hoy=pagos.filter(creado_en__date=hoy).aggregate(total=Sum("monto"))["total"] or 0,
        )
        return contexto


class ReportesView(RoleRequiredMixin, TemplateView):
    roles_permitidos = ROLES_ADMIN
    template_name = "reportes/reportes.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        ordenes = filtrar(Orden.objects, self.request, "mesa__sucursal__restaurante")
        pagos = filtrar(Pago.objects, self.request, "orden__mesa__sucursal__restaurante")
        contexto.update(
            ordenes_por_estado={
                estado: ordenes.filter(estado=estado).count()
                for estado, _ in Orden.ESTADO_CHOICES
            },
            ventas_por_metodo=(
                pagos.values("metodo_pago__nombre").annotate(total=Sum("monto"))
            ),
        )
        return contexto
