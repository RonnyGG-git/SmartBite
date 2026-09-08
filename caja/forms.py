from django import forms

from .models import MetodoPago


class CobrarOrdenForm(forms.Form):
    metodo_pago = forms.ModelChoiceField(queryset=MetodoPago.objects.filter(activo=True))
    monto = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    referencia_transaccion = forms.CharField(max_length=100, required=False)
