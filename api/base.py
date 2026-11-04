from core.tenancy import restaurantes_accesibles

ENCABEZADO_RESTAURANTE = "X-Restaurante"


class ConRestauranteMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        elegido = request.headers.get(ENCABEZADO_RESTAURANTE, "")
        if request.user.is_authenticated and elegido.isdigit():
            actual = restaurantes_accesibles(request.user).filter(pk=int(elegido)).first()
            if actual is not None:
                request._restaurante_actual = actual
