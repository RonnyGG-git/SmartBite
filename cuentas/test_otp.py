import json
import re
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.correo import URL_BREVO, BrevoBackend
from cuentas import otp
from cuentas.models import CodigoVerificacion, Rol, Usuario

CLAVE = "Clave-Segura-2026!"
NUEVA = "Otra-Clave-Segura-2027!"


def ultimo_codigo():
    return re.search(r"\b(\d{4})\b", mail.outbox[-1].body).group(1)


def otro_codigo(codigo):
    return f"{(int(codigo) + 1) % 10000:04d}"


class RegistroConCodigoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        Rol.objects.create(nombre="ADMINISTRADOR")

    def registrar(self, email="duena@test.co"):
        return self.client.post(reverse("cuentas:registro_admin"), {
            "nombre": "Dueña", "email": email, "password1": CLAVE, "password2": CLAVE,
        })

    def test_el_registro_crea_la_cuenta_inactiva_y_envia_el_codigo(self):
        respuesta = self.registrar()
        self.assertRedirects(respuesta, reverse("cuentas:verificar"))
        usuario = Usuario.objects.get(email="duena@test.co")
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.email_verificado)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["duena@test.co"])
        self.assertRegex(mail.outbox[0].body, r"\b\d{4}\b")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_el_codigo_no_se_guarda_en_texto_plano(self):
        self.registrar()
        registro = CodigoVerificacion.objects.get()
        self.assertNotEqual(registro.huella, ultimo_codigo())
        self.assertEqual(len(registro.huella), 64)

    def test_codigo_correcto_activa_e_inicia_sesion(self):
        self.registrar()
        respuesta = self.client.post(reverse("cuentas:verificar"), {"codigo": ultimo_codigo()})
        self.assertRedirects(respuesta, reverse("restaurantes:restaurante_crear"))
        usuario = Usuario.objects.get(email="duena@test.co")
        self.assertTrue(usuario.is_active)
        self.assertTrue(usuario.email_verificado)
        self.assertEqual(int(self.client.session["_auth_user_id"]), usuario.pk)

    def test_codigo_incorrecto_no_activa(self):
        self.registrar()
        respuesta = self.client.post(reverse("cuentas:verificar"), {"codigo": otro_codigo(ultimo_codigo())})
        self.assertContains(respuesta, "El código no es correcto")
        self.assertFalse(Usuario.objects.get(email="duena@test.co").is_active)

    def test_formato_invalido(self):
        self.registrar()
        respuesta = self.client.post(reverse("cuentas:verificar"), {"codigo": "12a"})
        self.assertContains(respuesta, "4")
        self.assertEqual(CodigoVerificacion.objects.get().intentos, 0)

    def test_cinco_intentos_bloquean_el_codigo(self):
        self.registrar()
        bueno = ultimo_codigo()
        for _ in range(otp.MAX_INTENTOS):
            self.client.post(reverse("cuentas:verificar"), {"codigo": otro_codigo(bueno)})
        respuesta = self.client.post(reverse("cuentas:verificar"), {"codigo": bueno})
        self.assertContains(respuesta, "Demasiados intentos")
        self.assertFalse(Usuario.objects.get(email="duena@test.co").is_active)

    def test_codigo_vencido(self):
        self.registrar()
        CodigoVerificacion.objects.update(expira_en=timezone.now() - timedelta(seconds=1))
        respuesta = self.client.post(reverse("cuentas:verificar"), {"codigo": ultimo_codigo()})
        self.assertContains(respuesta, "venció")

    def test_reenviar_respeta_la_espera_y_anula_el_codigo_anterior(self):
        self.registrar()
        anterior = ultimo_codigo()
        self.client.post(reverse("cuentas:verificar_reenviar"))
        self.assertEqual(len(mail.outbox), 1)
        CodigoVerificacion.objects.update(creado_en=timezone.now() - otp.ESPERA_REENVIO)
        self.client.post(reverse("cuentas:verificar_reenviar"))
        self.assertEqual(len(mail.outbox), 2)
        nuevo = ultimo_codigo()
        if nuevo != anterior:
            respuesta = self.client.post(reverse("cuentas:verificar"), {"codigo": anterior})
            self.assertContains(respuesta, "no es correcto")
        respuesta = self.client.post(reverse("cuentas:verificar"), {"codigo": nuevo})
        self.assertRedirects(respuesta, reverse("restaurantes:restaurante_crear"))

    def test_login_sin_verificar_pide_el_codigo(self):
        self.registrar()
        self.client.cookies.clear()
        CodigoVerificacion.objects.update(creado_en=timezone.now() - otp.ESPERA_REENVIO)
        respuesta = self.client.post(reverse("cuentas:login"), {"username": "duena@test.co", "password": CLAVE})
        self.assertRedirects(respuesta, reverse("cuentas:verificar"))
        self.assertEqual(len(mail.outbox), 2)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_sin_verificar_con_clave_mala_no_revela_nada(self):
        self.registrar()
        respuesta = self.client.post(reverse("cuentas:login"), {"username": "duena@test.co", "password": "mala"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Email o contraseña incorrectos")

    def test_se_puede_registrar_de_nuevo_un_correo_sin_verificar(self):
        self.registrar()
        self.client.cookies.clear()
        respuesta = self.registrar()
        self.assertRedirects(respuesta, reverse("cuentas:verificar"))
        self.assertEqual(Usuario.objects.filter(email="duena@test.co").count(), 1)

    def test_no_se_puede_registrar_un_correo_verificado(self):
        Usuario.objects.create_user("duena@test.co", "Dueña", CLAVE)
        respuesta = self.registrar()
        self.assertContains(respuesta, "Ya existe una cuenta con ese email")

    def test_verificar_sin_registro_previo_vuelve_al_login(self):
        self.assertRedirects(self.client.get(reverse("cuentas:verificar")), reverse("cuentas:login"))

    def test_los_usuarios_existentes_siguen_entrando(self):
        Usuario.objects.create_user("viejo@test.co", "Viejo", CLAVE, rol=Rol.objects.get(nombre="ADMINISTRADOR"))
        respuesta = self.client.post(reverse("cuentas:login"), {"username": "viejo@test.co", "password": CLAVE})
        self.assertRedirects(respuesta, reverse("reportes:dashboard"), fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)

    def test_si_falla_el_envio_avisa_sin_romper(self):
        with mock.patch("cuentas.otp.send_mail", side_effect=OSError("caída")):
            respuesta = self.registrar()
        self.assertRedirects(respuesta, reverse("cuentas:verificar"))
        self.assertFalse(CodigoVerificacion.objects.exists())
        self.client.post(reverse("cuentas:verificar_reenviar"))
        self.assertEqual(len(mail.outbox), 1)


class RecuperarContrasenaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user("cajero@test.co", "Cajero", CLAVE)

    def pedir(self, email="cajero@test.co"):
        return self.client.post(reverse("cuentas:recuperar"), {"email": email})

    def cambiar(self, codigo, clave=NUEVA):
        return self.client.post(reverse("cuentas:recuperar_codigo"), {
            "codigo": codigo, "new_password1": clave, "new_password2": clave,
        })

    def test_codigo_correcto_cambia_la_contrasena(self):
        self.assertRedirects(self.pedir(), reverse("cuentas:recuperar_codigo"))
        self.assertRedirects(self.cambiar(ultimo_codigo()), reverse("cuentas:login"))
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(NUEVA))

    def test_codigo_incorrecto_no_cambia_nada(self):
        self.pedir()
        respuesta = self.cambiar(otro_codigo(ultimo_codigo()))
        self.assertContains(respuesta, "no es correcto")
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(CLAVE))

    def test_el_codigo_sirve_una_sola_vez(self):
        self.pedir()
        codigo = ultimo_codigo()
        self.cambiar(codigo)
        self.client.post(reverse("cuentas:recuperar"), {"email": "cajero@test.co"})
        respuesta = self.cambiar(codigo, "Tercera-Clave-2028!")
        self.assertContains(respuesta, "venció")
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(NUEVA))

    def test_correo_desconocido_responde_igual_sin_enviar(self):
        respuesta = self.pedir("nadie@test.co")
        self.assertRedirects(respuesta, reverse("cuentas:recuperar_codigo"))
        self.assertEqual(len(mail.outbox), 0)
        respuesta = self.cambiar("1234")
        self.assertContains(respuesta, "no es correcto")

    def test_cuenta_desactivada_no_recibe_codigo(self):
        Usuario.objects.filter(pk=self.usuario.pk).update(is_active=False)
        self.pedir()
        self.assertEqual(len(mail.outbox), 0)

    def test_contrasena_debil_se_rechaza(self):
        self.pedir()
        respuesta = self.cambiar(ultimo_codigo(), "123")
        self.assertEqual(respuesta.status_code, 200)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(CLAVE))

    def test_sin_pedir_codigo_redirige(self):
        self.assertRedirects(self.client.get(reverse("cuentas:recuperar_codigo")), reverse("cuentas:recuperar"))

    def test_login_muestra_el_enlace(self):
        self.assertContains(self.client.get(reverse("cuentas:login")), reverse("cuentas:recuperar"))


class BrevoBackendTests(TestCase):

    @override_settings(BREVO_API_KEY="clave-de-prueba")
    def test_envia_por_la_api_de_brevo(self):
        respuesta = mock.MagicMock(status=201)
        respuesta.__enter__.return_value = respuesta
        mensaje = EmailMultiAlternatives(
            "Asunto", "Texto 1234", "Smart Bite <envios@test.co>", ["destino@test.co"],
        )
        mensaje.attach_alternative("<b>1234</b>", "text/html")
        with mock.patch("core.correo.urllib.request.urlopen", return_value=respuesta) as abrir:
            enviados = BrevoBackend().send_messages([mensaje])
        self.assertEqual(enviados, 1)
        peticion = abrir.call_args.args[0]
        self.assertEqual(peticion.full_url, URL_BREVO)
        self.assertEqual(peticion.get_header("Api-key"), "clave-de-prueba")
        cuerpo = json.loads(peticion.data)
        self.assertEqual(cuerpo["sender"], {"email": "envios@test.co", "name": "Smart Bite"})
        self.assertEqual(cuerpo["to"], [{"email": "destino@test.co"}])
        self.assertEqual(cuerpo["htmlContent"], "<b>1234</b>")

    @override_settings(BREVO_API_KEY="clave-de-prueba")
    def test_un_error_de_brevo_se_propaga(self):
        mensaje = EmailMultiAlternatives("Asunto", "Texto", "envios@test.co", ["destino@test.co"])
        with mock.patch("core.correo.urllib.request.urlopen", side_effect=OSError("401")):
            with self.assertLogs("core.correo", level="ERROR"):
                with self.assertRaises(OSError):
                    BrevoBackend().send_messages([mensaje])
