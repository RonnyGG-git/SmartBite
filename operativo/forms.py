from django import forms
from django.db.models import Q

from .models import Cliente, DetalleOrden, Mesa, Orden


class MesaForm(forms.ModelForm):
    class Meta:
        model = Mesa
        fields = ["numero", "capacidad", "sucursal", "activa"]


class ClienteRapidoForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ["nombre", "telefono", "email"]


class CrearOrdenForm(forms.ModelForm):
    class Meta:
        model = Orden
        fields = ["mesa", "cliente"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        con_orden_activa = Orden.objects.exclude(estado__in=[Orden.ENTREGADA, Orden.CANCELADA]).filter(
            mesa__isnull=False
        ).values("mesa_id")
        self.fields["mesa"].queryset = Mesa.objects.filter(activa=True).filter(
            Q(estado=Mesa.DISPONIBLE) | (Q(estado=Mesa.OCUPADA) & ~Q(pk__in=con_orden_activa))
        )
        self.fields["mesa"].required = True
        self.fields["cliente"].required = False


class AgregarProductoForm(forms.Form):
    producto = forms.ModelChoiceField(queryset=None)
    cantidad = forms.IntegerField(min_value=1, initial=1)

    def __init__(self, *args, **kwargs):
        productos_qs = kwargs.pop("productos_qs")
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = productos_qs


class CambiarEstadoOrdenForm(forms.Form):
    estado = forms.ChoiceField(choices=Orden.ESTADO_CHOICES)

    def __init__(self, *args, **kwargs):
        orden = kwargs.pop("orden", None)
        super().__init__(*args, **kwargs)
        if orden:
            destinos = Orden.TRANSICIONES_VALIDAS.get(orden.estado, [])
            self.fields["estado"].choices = [
                (valor, etiqueta)
                for valor, etiqueta in Orden.ESTADO_CHOICES
                if valor in destinos
            ]
