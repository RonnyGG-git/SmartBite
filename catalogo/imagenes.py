from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError

LADO_MAXIMO = 900
PESO_MAXIMO = 8 * 1024 * 1024
PIXELES_MAXIMOS = 40_000_000
CALIDAD_JPEG = 82


def _a_rgb(imagen):
    if imagen.mode in ("RGBA", "LA", "PA") or "transparency" in imagen.info:
        con_alfa = imagen.convert("RGBA")
        fondo = Image.new("RGB", con_alfa.size, (255, 255, 255))
        fondo.paste(con_alfa, mask=con_alfa.getchannel("A"))
        return fondo
    return imagen.convert("RGB")


def procesar_imagen(archivo):
    if archivo.size > PESO_MAXIMO:
        raise ValidationError("La imagen pesa más de 8 MB. Elige una más liviana.")
    try:
        archivo.seek(0)
        with Image.open(archivo) as original:
            if original.width * original.height > PIXELES_MAXIMOS:
                raise ValidationError("La imagen es demasiado grande. Usa una de menos de 40 megapíxeles.")
            original.draft("RGB", (LADO_MAXIMO * 2, LADO_MAXIMO * 2))
            imagen = _a_rgb(ImageOps.exif_transpose(original))
            imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.Resampling.LANCZOS)
            salida = BytesIO()
            imagen.save(salida, format="JPEG", quality=CALIDAD_JPEG, optimize=True)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as error:
        raise ValidationError("No pudimos leer esa imagen. Prueba con una foto JPG o PNG.") from error
    return salida.getvalue()
