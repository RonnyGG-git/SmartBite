from django.db.models import Q

SESION_RESTAURANTE = "restaurante_id"

RUTAS = {
    "restaurantes.sucursal": "restaurante",
    "catalogo.categoria": "restaurante",
    "catalogo.producto": "sucursal__restaurante",
    "inventario.iteminventario": "sucursal__restaurante",
    "inventario.proveedor": "restaurante",
    "operativo.mesa": "sucursal__restaurante",
    "operativo.cliente": "restaurante",
    "operativo.reserva": "mesa__sucursal__restaurante",
}


def restaurantes_accesibles(usuario):
    from restaurantes.models import Restaurante

    if not usuario.is_authenticated:
        return Restaurante.objects.none()
    if usuario.is_superuser:
        return Restaurante.objects.all()
    condicion = Q(administrador=usuario)
    if usuario.restaurante_id:
        condicion |= Q(pk=usuario.restaurante_id)
    if usuario.sucursal_id:
        condicion |= Q(sucursales=usuario.sucursal_id)
    return Restaurante.objects.filter(condicion).distinct()


def restaurante_actual(request):
    if not hasattr(request, "_restaurante_actual"):
        accesibles = restaurantes_accesibles(request.user).order_by("pk")
        elegido = request.session.get(SESION_RESTAURANTE)
        actual = accesibles.filter(pk=elegido).first() if elegido else None
        request._restaurante_actual = actual or accesibles.first()
    return request._restaurante_actual


def filtrar(queryset, request, ruta):
    if request.user.is_superuser:
        return queryset
    actual = restaurante_actual(request)
    if actual is None:
        return queryset.none()
    return queryset.filter(**{ruta: actual})


def limitar_opciones(form, request):
    from restaurantes.models import Restaurante

    for campo in form.fields.values():
        queryset = getattr(campo, "queryset", None)
        if queryset is None:
            continue
        if queryset.model is Restaurante:
            campo.queryset = queryset.filter(pk__in=restaurantes_accesibles(request.user).values("pk"))
            continue
        ruta = RUTAS.get(queryset.model._meta.label_lower)
        if ruta:
            campo.queryset = filtrar(queryset, request, ruta)
    return form


class RestauranteMixin:
    ruta_restaurante = None
    asignar_restaurante = False

    def get_queryset(self):
        return filtrar(super().get_queryset(), self.request, self.ruta_restaurante)

    def get_form(self, form_class=None):
        form = limitar_opciones(super().get_form(form_class), self.request)
        if self.asignar_restaurante and form.instance.restaurante_id is None:
            form.instance.restaurante = restaurante_actual(self.request)
        return form

    def form_valid(self, form):
        if self.asignar_restaurante and form.instance.restaurante_id is None:
            form.add_error(None, "Primero registra un restaurante.")
            return self.form_invalid(form)
        return super().form_valid(form)
