from datetime import date, datetime, timedelta
from unittest import mock

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from domicilio.models import Domicilio
from operativo.models import Mesa, Orden, Reserva

from .canal_twilio import firma_esperada
from .conversacion import Agente, iniciar_llamada
from .models import LineaTelefonica, Llamada
from .tests import AgenteTestCase
from .texto import extraer_fecha, extraer_hora, extraer_hora_suelta, extraer_personas, normalizar

TOKEN = "token-de-prueba"
BASE = "https://smartbite.test"
SANDBOX = "+14155238886"
CLIENTE = "+573001112233"


class FechasTests(SimpleTestCase):
    hoy = date(2026, 11, 10)

    def fecha(self, texto):
        return extraer_fecha(normalizar(texto), self.hoy)

    def hora(self, texto):
        return extraer_hora(normalizar(texto))

    def test_fechas(self):
        self.assertEqual(self.fecha("hoy"), self.hoy)
        self.assertEqual(self.fecha("mañana"), date(2026, 11, 11))
        self.assertEqual(self.fecha("pasado mañana"), date(2026, 11, 12))
        self.assertEqual(self.fecha("el viernes"), date(2026, 11, 13))
        self.assertEqual(self.fecha("el martes"), date(2026, 11, 17))
        self.assertEqual(self.fecha("el 20 de diciembre"), date(2026, 12, 20))
        self.assertEqual(self.fecha("el 5 de enero"), date(2027, 1, 5))
        self.assertEqual(self.fecha("para el 15"), date(2026, 11, 15))
        self.assertEqual(self.fecha("para el 3"), date(2026, 12, 3))

    def test_la_manana_no_es_el_dia_siguiente(self):
        self.assertIsNone(self.fecha("a las 10 de la mañana"))
        self.assertEqual(self.fecha("mañana a las 10 de la mañana"), date(2026, 11, 11))

    def test_fecha_imposible(self):
        self.assertIsNone(self.fecha("el 31 de febrero"))

    def test_horas(self):
        self.assertEqual(self.hora("a las 7 de la noche"), (19, 0))
        self.assertEqual(self.hora("a las siete y media"), (19, 30))
        self.assertEqual(self.hora("a las 10 de la mañana"), (10, 0))
        self.assertEqual(self.hora("7:30 pm"), (19, 30))
        self.assertEqual(self.hora("8pm"), (20, 0))
        self.assertEqual(self.hora("a las 20"), (20, 0))
        self.assertEqual(self.hora("al mediodía"), (12, 0))
        self.assertEqual(self.hora("a la una"), (13, 0))
        self.assertEqual(extraer_hora_suelta("8"), (20, 0))

    def test_personas(self):
        self.assertEqual(extraer_personas("para 4 personas"), 4)
        self.assertEqual(extraer_personas("somos cinco"), 5)
        self.assertEqual(extraer_personas("una mesa para dos"), 2)
        self.assertIsNone(extraer_personas("a las 8"))

    def test_las_personas_no_se_confunden_con_la_hora(self):
        self.assertIsNone(self.hora("las 3 personas"))


class ReservaPorAgenteTests(AgenteTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.mesa = Mesa.objects.create(numero=1, capacidad=6, sucursal=cls.sucursal)

    def agente(self):
        return self.nueva_llamada(telefono=CLIENTE)

    def test_reserva_paso_a_paso(self):
        agente = self.agente()
        self.assertIn("qué día", agente.procesar("Quiero reservar una mesa").texto)
        self.assertIn("qué hora", agente.procesar("el viernes").texto)
        self.assertIn("cuántas personas", agente.procesar("a las 8 de la noche").texto)
        self.assertIn("nombre", agente.procesar("4").texto)
        resumen = agente.procesar("Ana Pérez").texto
        self.assertIn("4 personas", resumen)
        self.assertIn("8:00 de la noche", resumen)
        self.assertFalse(Reserva.objects.exists())
        final = agente.procesar("sí")
        reserva = Reserva.objects.get()
        self.assertTrue(final.finalizar)
        self.assertIn(reserva.codigo, final.texto.replace(" ", ""))
        self.assertEqual(reserva.nombre, "Ana Pérez")
        self.assertEqual(timezone.localtime(reserva.fecha_hora).hour, 20)
        agente.llamada.refresh_from_db()
        self.assertEqual(agente.llamada.reserva, reserva)

    def test_todo_en_una_frase(self):
        agente = self.agente()
        respuesta = agente.procesar("Quiero reservar para 2 personas el viernes a las 7 de la noche a nombre de Luis")
        self.assertIn("2 personas", respuesta.texto)
        self.assertIn("¿Confirmas", respuesta.texto)

    def test_cambiar_la_hora_antes_de_confirmar(self):
        agente = self.agente()
        agente.procesar("Quiero reservar para 2 personas el viernes a las 7 de la noche a nombre de Luis")
        respuesta = agente.procesar("mejor a las 9 de la noche")
        self.assertIn("9:00 de la noche", respuesta.texto)
        self.assertFalse(Reserva.objects.exists())

    def test_no_se_registra_sin_confirmar(self):
        agente = self.agente()
        agente.procesar("Quiero reservar para 2 personas el viernes a las 7 de la noche a nombre de Luis")
        agente.procesar("no")
        self.assertFalse(Reserva.objects.exists())

    def test_sin_mesa_ofrece_otras_horas(self):
        agente = self.agente()
        agente.procesar("Quiero reservar para 2 personas el viernes a las 7 de la noche a nombre de Luis")
        agente.procesar("sí")
        otra = self.nueva_llamada("CA-2", telefono="+573009998877")
        otra.procesar("Quiero reservar para 2 personas el viernes a las 7 de la noche a nombre de Eva")
        respuesta = otra.procesar("sí")
        self.assertIn("no tenemos mesas", respuesta.texto)
        self.assertEqual(Reserva.objects.count(), 1)
        otra.llamada.refresh_from_db()
        self.assertEqual(otra.llamada.fase, Llamada.FASE_RESERVA_HORA)

    def test_grupo_mayor_que_las_mesas(self):
        agente = self.agente()
        agente.procesar("Quiero reservar para 20 personas el viernes a las 7 de la noche a nombre de Luis")
        respuesta = agente.procesar("sí")
        self.assertIn("cuántas personas", respuesta.texto)
        self.assertFalse(Reserva.objects.exists())

    def test_fecha_pasada_vuelve_a_preguntar(self):
        agente = self.agente()
        agente.procesar("Quiero reservar para 2 personas hoy a las 12 de la mañana a nombre de Luis")
        respuesta = agente.procesar("sí")
        self.assertIn("qué día", respuesta.texto)

    def test_cancelar_la_reserva_en_curso(self):
        agente = self.agente()
        agente.procesar("Quiero reservar una mesa")
        respuesta = agente.procesar("cancelar")
        self.assertIn("cancelé la reserva", respuesta.texto)
        agente.llamada.refresh_from_db()
        self.assertEqual(agente.llamada.fase, Llamada.FASE_PEDIDO)

    def test_una_persona_no_pide_operador(self):
        agente = self.agente()
        agente.procesar("Quiero reservar una mesa")
        agente.procesar("el viernes")
        agente.procesar("a las 8")
        respuesta = agente.procesar("para una persona")
        self.assertIn("nombre", respuesta.texto)

    def test_con_pedido_en_curso_no_mezcla(self):
        agente = self.agente()
        agente.procesar("Quiero una Coca-Cola")
        self.assertIn("terminemos tu pedido", agente.procesar("quiero reservar una mesa").texto)


class DomicilioPorAgenteTests(AgenteTestCase):
    def preparar(self):
        agente = self.nueva_llamada(telefono=CLIENTE)
        agente.procesar("Quiero un domicilio")
        agente.procesar("una Coca-Cola")
        agente.procesar("eso es todo")
        return agente, agente.procesar("Me llamo Ana Pérez")

    def test_domicilio_sin_cuenta(self):
        agente, respuesta = self.preparar()
        self.assertIn("dirección de entrega", respuesta.texto)
        self.assertIn("referencia", agente.procesar("Calle 10 número 5 20").texto)
        resumen = agente.procesar("Torre 2 apartamento 301").texto
        self.assertIn("a domicilio en Calle 10", resumen)
        self.assertFalse(Orden.objects.exists())
        final = agente.procesar("sí")
        domicilio = Domicilio.objects.get()
        self.assertIsNone(domicilio.cliente)
        self.assertIsNone(domicilio.latitud)
        self.assertFalse(domicilio.tiene_ubicacion)
        self.assertEqual(domicilio.nombre_cliente, "Ana Pérez")
        self.assertEqual(domicilio.referencia, "Torre 2 apartamento 301")
        self.assertEqual(domicilio.orden.tipo_consumo, Orden.DOMICILIO)
        self.assertEqual(domicilio.orden.estado, Orden.POR_CONFIRMAR)
        self.assertEqual(domicilio.estado, Domicilio.SOLICITADO)
        self.assertIn(" ".join(domicilio.codigo_entrega), final.texto)

    def test_direccion_demasiado_corta(self):
        agente, _ = self.preparar()
        self.assertIn("No entendí la dirección", agente.procesar("aqui").texto)

    def test_sin_referencia(self):
        agente, _ = self.preparar()
        agente.procesar("Calle 10 número 5 20")
        self.assertIn("¿Confirmas", agente.procesar("no").texto)

    def test_ubicacion_reemplaza_la_direccion(self):
        agente, _ = self.preparar()
        respuesta = agente.procesar("", ubicacion=(4.6, -74.08))
        self.assertIn("referencia", respuesta.texto)
        agente.procesar("no")
        agente.procesar("sí")
        domicilio = Domicilio.objects.get()
        self.assertTrue(domicilio.tiene_ubicacion)
        self.assertEqual(str(domicilio.latitud), "4.600000")

    def test_no_se_duplica_al_reconfirmar(self):
        agente, _ = self.preparar()
        agente.procesar("Calle 10 número 5 20")
        agente.procesar("no")
        agente.procesar("sí")
        agente.herramientas.confirmar_pedido(True)
        self.assertEqual(Domicilio.objects.count(), 1)


@override_settings(TWILIO_AUTH_TOKEN=TOKEN, TWILIO_WEBHOOK_BASE=BASE)
class WebhookTestCase(AgenteTestCase):
    def enviar(self, nombre, datos, firma=None):
        ruta = reverse(f"agente_telefonico:{nombre}")
        cabecera = firma if firma is not None else firma_esperada(f"{BASE}{ruta}", datos, TOKEN)
        return self.client.post(ruta, datos, headers={"X-Twilio-Signature": cabecera})

    def setUp(self):
        self.linea = LineaTelefonica.objects.create(numero=SANDBOX, sucursal=self.sucursal)

    def texto(self, respuesta):
        return respuesta.content.decode("utf-8")


class FirmaTests(WebhookTestCase):
    def test_vector_oficial_de_twilio(self):
        datos = {"CallSid": "CA1234567890ABCDE", "Caller": "+14158675310", "Digits": "1234", "From": "+14158675310", "To": "+18005551212"}
        self.assertEqual(
            firma_esperada("https://mycompany.com/myapp.php?foo=1&bar=2", datos, "12345"),
            "GvWf1cFY/Q7PnoempGyD5oXAezc=",
        )

    def test_firma_falsa_se_rechaza(self):
        respuesta = self.enviar("twilio_whatsapp", {"From": f"whatsapp:{CLIENTE}", "To": f"whatsapp:{SANDBOX}", "Body": "hola"}, firma="falsa")
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Llamada.objects.exists())

    def test_datos_alterados_se_rechazan(self):
        datos = {"From": f"whatsapp:{CLIENTE}", "To": f"whatsapp:{SANDBOX}", "Body": "hola"}
        ruta = reverse("agente_telefonico:twilio_whatsapp")
        firma = firma_esperada(f"{BASE}{ruta}", datos, TOKEN)
        respuesta = self.client.post(ruta, {**datos, "Body": "otra cosa"}, headers={"X-Twilio-Signature": firma})
        self.assertEqual(respuesta.status_code, 403)

    @override_settings(TWILIO_AUTH_TOKEN="")
    def test_sin_token_configurado_todo_se_rechaza(self):
        datos = {"To": SANDBOX}
        respuesta = self.enviar("twilio_voz", datos, firma="cualquiera")
        self.assertEqual(respuesta.status_code, 403)

    def test_solo_acepta_post(self):
        self.assertEqual(self.client.get(reverse("agente_telefonico:twilio_voz")).status_code, 405)


class WhatsAppTests(WebhookTestCase):
    numero_mensaje = 0

    def mensaje(self, cuerpo="", sid=None, **extra):
        WhatsAppTests.numero_mensaje += 1
        datos = {
            "From": f"whatsapp:{CLIENTE}", "To": f"whatsapp:{SANDBOX}", "Body": cuerpo,
            "MessageSid": sid or f"SM{WhatsAppTests.numero_mensaje}", **extra,
        }
        return self.texto(self.enviar("twilio_whatsapp", datos))

    def test_saludo(self):
        self.assertIn("Bienvenido a Smart Bite", self.mensaje("Hola"))
        llamada = Llamada.objects.get()
        self.assertEqual(llamada.canal, Llamada.CANAL_WHATSAPP)
        self.assertEqual(llamada.telefono_origen, CLIENTE)

    def test_primer_mensaje_ya_trae_el_pedido(self):
        contenido = self.mensaje("Quiero una Coca-Cola")
        self.assertIn("Bienvenido", contenido)
        self.assertIn("Agregué", contenido)

    def test_una_respuesta_no_se_toma_como_nombre(self):
        self.mensaje("Quiero una Coca-Cola")
        self.assertIn("nombre", self.mensaje("eso es todo"))
        for respuesta in ("sí", "para llevar"):
            self.assertIn("Necesito un nombre", self.mensaje(respuesta))
        self.assertEqual(Llamada.objects.get().nombre_cliente, "")
        self.assertIn("recoger", self.mensaje("Carlos Pérez"))
        self.assertEqual(Llamada.objects.get().nombre_cliente, "Carlos Pérez")

    def test_mismo_hilo_en_varios_mensajes(self):
        self.mensaje("Hola")
        self.mensaje("una Coca-Cola")
        self.assertEqual(Llamada.objects.count(), 1)

    def test_mensaje_repetido_no_se_procesa_dos_veces(self):
        self.mensaje("Hola", sid="SMA")
        self.mensaje("una Coca-Cola", sid="SMB")
        self.mensaje("una Coca-Cola", sid="SMB")
        self.assertEqual(Llamada.objects.get().items, {str(self.coca.pk): 1})

    def test_primer_mensaje_repetido_no_crea_otra_sesion(self):
        self.mensaje("Hola", sid="SMA")
        Llamada.objects.update(estado=Llamada.FINALIZADA)
        contenido = self.mensaje("Hola", sid="SMA")
        self.assertEqual(Llamada.objects.count(), 1)
        self.assertNotIn("Message", contenido)

    def test_sesion_vieja_se_cierra(self):
        self.mensaje("una Coca-Cola")
        Llamada.objects.update(actualizado_en=timezone.now() - timedelta(hours=2))
        self.mensaje("Hola")
        self.assertEqual(Llamada.objects.count(), 2)
        self.assertEqual(Llamada.objects.order_by("pk").first().estado, Llamada.CORTADA)

    def test_nota_de_voz_no_se_entiende(self):
        self.assertIn("solo puedo leer", self.mensaje("", NumMedia="1"))

    def test_numero_sin_configurar(self):
        datos = {"From": f"whatsapp:{CLIENTE}", "To": "whatsapp:+10000000000", "Body": "Hola", "MessageSid": "SMX"}
        self.assertIn("no está configurado", self.texto(self.enviar("twilio_whatsapp", datos)))
        self.assertFalse(Llamada.objects.exists())

    def test_texto_del_cliente_se_escapa(self):
        contenido = self.mensaje("<Hangup/> quiero <b>algo</b>")
        self.assertNotIn("<Hangup", contenido)

    def test_domicilio_con_ubicacion_de_whatsapp(self):
        self.mensaje("Quiero un domicilio")
        self.mensaje("una Coca-Cola")
        self.mensaje("eso es todo")
        self.assertIn("compartir tu ubicación", self.mensaje("Me llamo Ana Pérez"))
        self.assertIn("referencia", self.mensaje("", Latitude="4.6", Longitude="-74.08"))
        self.mensaje("no")
        self.assertIn("código", self.mensaje("sí"))
        self.assertTrue(Domicilio.objects.get().tiene_ubicacion)

    def test_reserva_por_whatsapp(self):
        Mesa.objects.create(numero=1, capacidad=6, sucursal=self.sucursal)
        self.mensaje("Hola")
        self.mensaje("Quiero reservar para 2 personas el viernes a las 7 de la noche a nombre de Luis")
        contenido = self.mensaje("sí")
        reserva = Reserva.objects.get()
        self.assertIn(reserva.codigo, contenido)
        self.assertEqual(reserva.telefono, CLIENTE)


class VozTests(WebhookTestCase):
    def llamar(self):
        return self.texto(self.enviar("twilio_voz", {"CallSid": "CA1", "From": CLIENTE, "To": SANDBOX}))

    def hablar(self, texto):
        return self.texto(self.enviar("twilio_voz_turno", {"CallSid": "CA1", "SpeechResult": texto}))

    def test_contesta_y_escucha(self):
        contenido = self.llamar()
        self.assertIn("Bienvenido", contenido)
        self.assertIn('input="speech"', contenido)
        self.assertIn(reverse("agente_telefonico:twilio_voz_turno"), contenido)
        self.assertEqual(Llamada.objects.get().telefono_origen, CLIENTE)

    def test_webhook_repetido_no_duplica(self):
        self.llamar()
        self.llamar()
        self.assertEqual(Llamada.objects.count(), 1)

    def test_turno_agrega_el_producto(self):
        self.llamar()
        self.assertIn("Agregué", self.hablar("una Coca-Cola"))

    def test_silencios_cuelgan(self):
        self.llamar()
        self.hablar("")
        self.hablar("")
        self.assertIn("<Hangup", self.hablar(""))

    def test_transferir_a_operador(self):
        self.linea.numero_transferencia = "+573005550000"
        self.linea.save()
        self.llamar()
        self.assertIn("<Dial>+573005550000</Dial>", self.hablar("quiero hablar con un asesor"))

    def test_linea_apagada(self):
        self.linea.activa = False
        self.linea.save()
        self.assertIn("<Hangup", self.llamar())

    def test_colgar_cierra_la_llamada(self):
        self.llamar()
        self.enviar("twilio_voz_estado", {"CallSid": "CA1", "CallStatus": "completed"})
        self.assertEqual(Llamada.objects.get().estado, Llamada.CORTADA)

    def test_llamada_desconocida(self):
        self.assertIn("<Hangup", self.texto(self.enviar("twilio_voz_turno", {"CallSid": "NOEXISTE"})))

    def test_codigo_de_reserva_se_deletrea(self):
        Mesa.objects.create(numero=1, capacidad=6, sucursal=self.sucursal)
        self.llamar()
        self.hablar("Quiero reservar para 2 personas el viernes a las 7 de la noche a nombre de Luis")
        contenido = self.hablar("sí")
        self.assertIn(" ".join(Reserva.objects.get().codigo), contenido)


class PanelDomicilioTests(AgenteTestCase):
    def test_panel_y_seguimiento_sin_mapa(self):
        agente = self.nueva_llamada(telefono=CLIENTE)
        agente.procesar("Quiero un domicilio")
        agente.procesar("una Coca-Cola")
        agente.procesar("eso es todo")
        agente.procesar("Me llamo Ana Pérez")
        agente.procesar("Calle 10 número 5 20")
        agente.procesar("no")
        agente.procesar("sí")
        domicilio = Domicilio.objects.get()
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse("domicilio:panel")), "Ana Pérez")
        seguimiento = self.client.get(reverse("domicilio:seguimiento", args=[domicilio.pk]))
        self.assertContains(seguimiento, "no tiene punto en el mapa")
        self.assertContains(seguimiento, 'data-destino-lat=""')
