from urllib.parse import urlsplit

from django import forms
from django.db import transaction
from django.utils import timezone

from .imagenes import procesar_imagen
from .models import Categoria, ImagenProducto, Producto
from .widgets import SelectorImagen


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre"]

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        repetida = Categoria.objects.filter(restaurante=self.instance.restaurante, nombre__iexact=nombre)
        if repetida.exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una categoría con ese nombre en tu restaurante.")
        return nombre


class ProductoForm(forms.ModelForm):
    archivo_imagen = forms.ImageField(
        required=False,
        label="Imagen del platillo",
        widget=SelectorImagen,
        help_text="Sube una imagen descargada o toma una foto. Máximo 8 MB.",
    )
    quitar_imagen = forms.BooleanField(required=False, label="Quitar la imagen actual")

    field_order = [
        "nombre", "descripcion", "precio", "categoria", "sucursal", "archivo_imagen", "url_imagen",
        "quitar_imagen", "disponible",
    ]

    class Meta:
        model = Producto
        fields = ["nombre", "descripcion", "precio", "url_imagen", "categoria", "sucursal", "disponible"]
        labels = {"url_imagen": "O pega el enlace de una imagen"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.imagen_procesada = None
        self.fields["archivo_imagen"].widget.imagen_actual = self.instance.imagen_src if self.instance.pk else ""
        if not (self.instance.pk and self.instance.imagen_src):
            del self.fields["quitar_imagen"]

    def clean_archivo_imagen(self):
        archivo = self.cleaned_data.get("archivo_imagen")
        if archivo:
            self.imagen_procesada = procesar_imagen(archivo)
        return archivo

    def clean_url_imagen(self):
        url = self.cleaned_data["url_imagen"]
        if url and urlsplit(url).scheme not in ("http", "https"):
            raise forms.ValidationError("El enlace debe empezar por http:// o https://.")
        return url

    @transaction.atomic
    def save(self, commit=True):
        producto = super().save(commit=False)
        quitar = self.cleaned_data.get("quitar_imagen")
        if self.imagen_procesada:
            producto.url_imagen = ""
            producto.imagen_version = int(timezone.now().timestamp())
        elif quitar:
            producto.url_imagen = ""
            producto.imagen_version = 0
        elif producto.url_imagen:
            producto.imagen_version = 0
        producto.save()
        self.save_m2m()
        if self.imagen_procesada:
            ImagenProducto.objects.update_or_create(producto=producto, defaults={"datos": self.imagen_procesada})
        elif not producto.imagen_version:
            ImagenProducto.objects.filter(producto=producto).delete()
        return producto
