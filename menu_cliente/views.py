from django.shortcuts import get_object_or_404, render

from catalogo.models import Categoria, Producto
from operativo.models import Mesa


def menu(request):
    """Vista pública (sin login) — accedida vía el QR generado por operativo.generar_qr."""
    mesa_id = request.GET.get("mesa")
    mesa = get_object_or_404(Mesa, pk=mesa_id) if mesa_id else None

    productos_qs = Producto.objects.filter(disponible=True)
    if mesa:
        productos_qs = productos_qs.filter(sucursal=mesa.sucursal)

    categorias = Categoria.objects.prefetch_related(
        "productos"
    ).filter(productos__in=productos_qs).distinct()

    return render(request, "menu_cliente/menu.html", {"mesa": mesa, "categorias": categorias})
