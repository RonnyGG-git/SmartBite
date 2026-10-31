from django.shortcuts import redirect


def menu(request):
    mesa_id = request.GET.get("mesa", "")
    if mesa_id.isdigit():
        return redirect("cliente:mesa", mesa_id=int(mesa_id))
    return redirect("cliente:menu")
