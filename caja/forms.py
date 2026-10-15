from decimal import Decimal

from django import forms

from .models import MetodoPago


class CobrarOrdenForm(forms.Form):
    metodo_pago = forms.ModelChoiceField(queryset=MetodoPago.objects.filter(activo=True))
    monto = forms.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"), label="Monto a abonar")
    propina = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, initial=0,
        help_text="No abona a la cuenta; se registra aparte.",
    )
    referencia_transaccion = forms.CharField(max_length=100, required=False, label="Referencia (opcional)")
    efectivo_recibido = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False,
        help_text="Solo efectivo: para calcular el cambio.",
    )

    def clean_propina(self):
        return self.cleaned_data.get("propina") or Decimal("0")