from django.shortcuts import redirect


def menu(request):
    """Compatibilidad con los QR impresos antes del módulo `cliente`
    (apuntaban a /menu/?mesa=<id>). El menú público ahora vive en cliente."""
    mesa_id = request.GET.get("mesa", "")
    if mesa_id.isdigit():
        return redirect("cliente:mesa", mesa_id=int(mesa_id))
    return redirect("cliente:menu")
