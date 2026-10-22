from .tenancy import restaurante_actual


def restaurante(request):
    if not request.user.is_authenticated:
        return {}
    return {"restaurante_actual": restaurante_actual(request)}
