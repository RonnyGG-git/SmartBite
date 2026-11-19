from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from catalogo.models import ImagenProducto
from core.testing import crear_escenario, crear_usuario


def imagen_subida(ancho=1600, alto=1200, formato="PNG", modo="RGBA", nombre="plato.png"):
    salida = BytesIO()
    Image.new(modo, (ancho, alto), (200, 100, 50, 255) if modo == "RGBA" else (200, 100, 50)).save(salida, format=formato)
    return SimpleUploadedFile(nombre, salida.getvalue(), content_type=f"image/{formato.lower()}")


class ImagenProductoTests(TestCase):
    def setUp(self):
        self.d = crear_escenario()
        self.producto = self.d["bandeja"]
        self.client.force_login(crear_usuario("JEFE_COCINA"))
        self.url = reverse("catalogo:producto_editar", args=[self.producto.pk])

    def datos(self, **extra):
        return {
            "nombre": self.producto.nombre, "descripcion": "", "precio": "32000", "url_imagen": "",
            "categoria": self.d["categoria"].pk, "sucursal": self.d["centro"].pk, "disponible": "on", **extra,
        }

    def test_cocina_sube_imagen_y_se_reduce_a_jpeg(self):
        respuesta = self.client.post(self.url, self.datos(archivo_imagen=imagen_subida()))
        self.assertEqual(respuesta.status_code, 302)
        self.producto.refresh_from_db()
        self.assertGreater(self.producto.imagen_version, 0)
        guardada = Image.open(BytesIO(bytes(self.producto.imagen.datos)))
        self.assertEqual(guardada.format, "JPEG")
        self.assertLessEqual(max(guardada.size), 900)

    def test_la_imagen_se_sirve_sin_sesion_con_cache(self):
        self.client.post(self.url, self.datos(archivo_imagen=imagen_subida()))
        self.producto.refresh_from_db()
        self.client.logout()
        respuesta = self.client.get(self.producto.imagen_src)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "image/jpeg")
        self.assertIn("immutable", respuesta["Cache-Control"])

    def test_archivo_que_no_es_imagen_se_rechaza(self):
        falso = SimpleUploadedFile("plato.png", b"esto no es una imagen", content_type="image/png")
        respuesta = self.client.post(self.url, self.datos(archivo_imagen=falso))
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(ImagenProducto.objects.filter(producto=self.producto).exists())

    def test_url_de_imagen_reemplaza_la_subida(self):
        self.client.post(self.url, self.datos(archivo_imagen=imagen_subida()))
        self.client.post(self.url, self.datos(url_imagen="https://ejemplo.co/plato.jpg"))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.imagen_src, "https://ejemplo.co/plato.jpg")
        self.assertFalse(ImagenProducto.objects.filter(producto=self.producto).exists())

    def test_url_que_no_es_http_se_rechaza(self):
        respuesta = self.client.post(self.url, self.datos(url_imagen="ftp://ejemplo.co/plato.jpg"))
        self.assertEqual(respuesta.status_code, 200)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.url_imagen, "")

    def test_quitar_imagen(self):
        self.client.post(self.url, self.datos(archivo_imagen=imagen_subida()))
        self.client.post(self.url, self.datos(quitar_imagen="on"))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.imagen_src, "")
        self.assertFalse(ImagenProducto.objects.filter(producto=self.producto).exists())

    def test_editar_sin_tocar_la_imagen_la_conserva(self):
        self.client.post(self.url, self.datos(archivo_imagen=imagen_subida()))
        self.producto.refresh_from_db()
        version = self.producto.imagen_version
        self.client.post(self.url, self.datos(descripcion="Con chicharrón"))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.imagen_version, version)
        self.assertTrue(ImagenProducto.objects.filter(producto=self.producto).exists())

    def test_formulario_es_multipart_y_ofrece_camara(self):
        respuesta = self.client.get(self.url)
        self.assertContains(respuesta, 'enctype="multipart/form-data"')
        self.assertContains(respuesta, "data-abrir-camara")

    def test_menu_del_cliente_muestra_la_imagen(self):
        self.client.post(self.url, self.datos(archivo_imagen=imagen_subida()))
        self.producto.refresh_from_db()
        self.client.logout()
        self.client.get(reverse("cliente:mesa", args=[self.d["mesa"].pk]))
        self.client.post(reverse("cliente:tipo_consumo"), {"tipo": "EN_RESTAURANTE"})
        self.assertContains(self.client.get(reverse("cliente:menu")), self.producto.imagen_src)
