import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone
from django.utils.formats import date_format

from operativo.models import Orden

from .herramientas import Herramientas, ultimos_digitos
from .interprete import interpretar
from .models import Llamada, TurnoLlamada
from .texto import (
    contiene,
    enmascarar_tarjetas,
    extraer_cantidad,
    extraer_fecha,
    extraer_hora,
    extraer_hora_suelta,
    extraer_personas,
    extraer_telefono,
    formatear_pesos,
)

logger = logging.getLogger(__name__)

MOTIVOS_NO_AGREGADO = {
    "NO_DISPONIBLE": "no está disponible en este momento",
    "SIN_STOCK": "está agotado en este momento",
    "NO_EXISTE": "no está en el menú",
    "CANTIDAD_INVALIDA": "no se puede pedir en esa cantidad; el máximo es 50 por producto",
}
AVISO_PRECIOS = "Los precios los calcula el sistema del restaurante y no puedo cambiarlos. "
MAX_PRODUCTOS_LEIDOS = 8
PREFIJO_NOMBRE = re.compile(r"^\s*(?:(?:me llamo|mi nombre es|a nombre de|soy|es|el|la)\s+)+", re.IGNORECASE)
LARGO_MINIMO_DIRECCION = 8
DIRECCION_POR_UBICACION = "Ubicación compartida por WhatsApp"
PREGUNTA_MODALIDAD = "¿Lo vas a recoger en el restaurante, lo vas a comer allá o te lo llevamos a domicilio?"


@dataclass
class Respuesta:
    texto: str
    finalizar: bool = False
    transferir_a: str = ""


def _max_silencios():
    return getattr(settings, "AGENTE_MAX_SILENCIOS", 3)


def _max_turnos():
    return getattr(settings, "AGENTE_MAX_TURNOS", 60)


def iniciar_llamada(sucursal, identificador, canal=Llamada.CANAL_TELEFONO, telefono_origen="", linea=None):
    return Llamada.objects.get_or_create(
        identificador=identificador,
        defaults={
            "sucursal": sucursal,
            "canal": canal,
            "telefono_origen": telefono_origen[:20],
            "telefono_contacto": telefono_origen[:20],
            "linea": linea,
        },
    )


def _cantidad_texto(cantidad):
    return str(cantidad)


def _lista(partes):
    if len(partes) <= 1:
        return "".join(partes)
    return ", ".join(partes[:-1]) + " y " + partes[-1]


def _hora_texto(hora, minuto):
    parte = "de la mañana" if hora < 12 else "de la tarde" if hora < 19 else "de la noche"
    return f"{hora % 12 or 12}:{minuto:02d} {parte}"


class Agente:
    def __init__(self, llamada):
        self.llamada = llamada
        self.herramientas = Herramientas(llamada)
        self.ubicacion = None

    def _registrar(self, rol, texto):
        TurnoLlamada.objects.create(llamada=self.llamada, rol=rol, texto=enmascarar_tarjetas(texto)[:2000])

    def _guardar(self, *campos):
        self.llamada.save(update_fields=[*campos, "actualizado_en"])

    def _cerrar(self, estado, error=""):
        self.llamada.estado = estado
        self.llamada.fase = Llamada.FASE_CERRADA
        self.llamada.finalizada_en = timezone.now()
        campos = ["estado", "fase", "finalizada_en"]
        if error:
            self.llamada.error = error[:300]
            campos.append("error")
        if self.llamada.orden_id is None:
            self.llamada.items = {}
            campos.append("items")
        self._guardar(*campos)

    def iniciar(self):
        restaurante = self.llamada.sucursal.restaurante.nombre
        if self.llamada.linea and not self.llamada.linea.activa:
            texto = (
                f"Hola, te comunicaste con {restaurante}. En este momento no estamos recibiendo pedidos "
                "automáticos. Por favor llámanos más tarde. Gracias."
            )
            self._registrar(TurnoLlamada.AGENTE, texto)
            self._cerrar(Llamada.FINALIZADA, "Agente desactivado para esta línea.")
            return Respuesta(texto, finalizar=True)
        texto = (
            f"¡Hola! Bienvenido a {restaurante}. Soy el asistente virtual del restaurante. "
            "Guardamos esta conversación solo para gestionar tu solicitud. "
            "Puedo tomar tu pedido, enviarlo a domicilio o reservarte una mesa. ¿Qué necesitas hoy?"
        )
        if not self.llamada.turnos.exists():
            self._registrar(TurnoLlamada.AGENTE, texto)
        return Respuesta(texto)

    def colgar(self):
        if self.llamada.abierta:
            self._cerrar(Llamada.CORTADA)

    def procesar(self, texto, ubicacion=None):
        self.llamada.refresh_from_db()
        self.herramientas.llamada = self.llamada
        self.ubicacion = ubicacion
        if not self.llamada.abierta:
            return Respuesta("Esta llamada ya terminó.", finalizar=True)
        if texto or ubicacion:
            self._registrar(TurnoLlamada.CLIENTE, texto or "[Ubicación compartida]")
        try:
            if self.llamada.turnos.filter(rol=TurnoLlamada.CLIENTE).count() > _max_turnos():
                self._cerrar(Llamada.FINALIZADA, "Se alcanzó el máximo de turnos por llamada.")
                respuesta = Respuesta(
                    "La llamada se extendió demasiado y debo finalizarla. Por favor vuelve a llamarnos.", finalizar=True
                )
            else:
                respuesta = self._responder(texto)
        except DatabaseError:
            logger.exception("Error de base de datos en la llamada %s", self.llamada.identificador)
            respuesta = Respuesta(
                "Tengo un problema técnico consultando el sistema y no registré ningún pedido. "
                "Por favor intenta de nuevo en un momento."
            )
            try:
                Llamada.objects.filter(pk=self.llamada.pk).update(error="Error de base de datos durante la llamada.")
            except DatabaseError:
                pass
            return respuesta
        self._registrar(TurnoLlamada.AGENTE, respuesta.texto)
        return respuesta

    def _guardar_ubicacion(self):
        latitud, longitud = self.ubicacion
        self.llamada.latitud = Decimal(f"{latitud:.6f}")
        self.llamada.longitud = Decimal(f"{longitud:.6f}")
        self.llamada.resumen_leido = False
        self._guardar("latitud", "longitud", "resumen_leido")

    def _tras_ubicacion(self):
        if self.llamada.silencios:
            self.llamada.silencios = 0
            self._guardar("silencios")
        if self.llamada.tipo_consumo == Orden.DOMICILIO and self.llamada.items:
            respuesta = self._siguiente_paso()
            respuesta.texto = "Recibí tu ubicación. " + respuesta.texto
            return respuesta
        return Respuesta("Recibí tu ubicación. ¿Qué te gustaría ordenar a domicilio?")

    def _responder(self, texto):
        if self.ubicacion:
            self._guardar_ubicacion()
            if not (texto or "").strip():
                return self._tras_ubicacion()
        intencion = interpretar(texto, self.herramientas)

        if intencion.tipo == "VACIO":
            self.llamada.silencios += 1
            self._guardar("silencios")
            if self.llamada.silencios >= _max_silencios():
                self._cerrar(Llamada.FINALIZADA, "Cliente sin respuesta.")
                return Respuesta(
                    "Como no te escucho, voy a finalizar la llamada. Puedes llamarnos de nuevo cuando quieras.",
                    finalizar=True,
                )
            return Respuesta("¿Sigues ahí? No te escuché. ¿Qué te gustaría ordenar?")
        if self.llamada.silencios:
            self.llamada.silencios = 0
            self._guardar("silencios")

        prefijo = AVISO_PRECIOS if intencion.sospecha_precio else ""

        if intencion.tipo == "HUMANO":
            return self._transferir()
        if intencion.tipo == "ESTADO" or (self.llamada.pendiente.get("estado") and intencion.normal.isdigit()):
            return self._estado(intencion.numero or (int(intencion.normal) if intencion.normal.isdigit() else None))
        if intencion.tipo == "CANCELAR":
            en_reserva = self.llamada.fase in Llamada.FASES_RESERVA
            self.herramientas.cancelar_borrador_pedido()
            self._ir_a(Llamada.FASE_PEDIDO)
            if en_reserva:
                return Respuesta("Listo, cancelé la reserva y no se registró nada. ¿Te ayudo con algo más?")
            return Respuesta("Listo, cancelé el pedido y no se registró nada. ¿Quieres pedir algo diferente?")

        manejadores = {
            Llamada.FASE_CONFIRMACION: self._en_confirmacion,
            Llamada.FASE_DATOS_REGISTRADOS: self._en_datos_registrados,
            Llamada.FASE_NOMBRE: self._en_nombre,
            Llamada.FASE_TELEFONO: self._en_telefono,
            Llamada.FASE_MODALIDAD: self._en_modalidad,
            Llamada.FASE_DIRECCION: self._en_direccion,
            Llamada.FASE_REFERENCIA: self._en_referencia,
        }
        manejadores.update(dict.fromkeys(Llamada.FASES_RESERVA, self._en_reserva))
        manejador = manejadores.get(self.llamada.fase)
        if manejador:
            respuesta = manejador(intencion)
            if respuesta:
                respuesta.texto = prefijo + respuesta.texto
                return respuesta

        respuesta = self._general(intencion)
        respuesta.texto = prefijo + respuesta.texto
        return respuesta

    def _ir_a(self, fase):
        self.llamada.fase = fase
        self._guardar("fase")

    def _transferir(self):
        destino = self.llamada.linea.numero_transferencia if self.llamada.linea else ""
        if destino:
            self._cerrar(Llamada.TRANSFERIDA)
            return Respuesta("Te comunico con una persona del restaurante. Un momento, por favor.", finalizar=True, transferir_a=destino)
        return Respuesta(
            "En este momento no hay un operador disponible, pero yo puedo tomar tu pedido. ¿Qué te gustaría ordenar?"
        )

    def _estado(self, numero):
        if not numero:
            self.llamada.pendiente = {"estado": True}
            self._guardar("pendiente")
            return Respuesta("Claro. ¿Cuál es el número de tu pedido?")
        self.llamada.pendiente = {}
        self._guardar("pendiente")
        resultado = self.herramientas.consultar_estado_pedido(numero)
        if not resultado["encontrado"]:
            return Respuesta(
                f"No encontré un pedido número {numero} asociado a tu teléfono. ¿Te ayudo con algo más?"
            )
        return Respuesta(f"Tu pedido número {numero} está {resultado['estado_texto'].lower()}. ¿Te ayudo con algo más?")

    def _en_confirmacion(self, intencion):
        if intencion.productos or intencion.tipo in ("ELIMINAR", "MODIFICAR", "OBSERVACION", "MODALIDAD"):
            self._ir_a(Llamada.FASE_PEDIDO)
            return None
        if intencion.niega and not intencion.afirma:
            self._ir_a(Llamada.FASE_PEDIDO)
            self.llamada.resumen_leido = False
            self._guardar("resumen_leido")
            return Respuesta("De acuerdo, todavía no lo registro. ¿Qué quieres cambiar?")
        if intencion.afirma:
            return self._confirmar()
        return Respuesta("Para registrarlo necesito que me digas sí o no. ¿Confirmas el pedido?")

    def _confirmar(self):
        resultado = self.herramientas.confirmar_pedido(True)
        self.llamada = self.herramientas.llamada
        if resultado["ok"]:
            self._cerrar(Llamada.FINALIZADA)
            numero = resultado["pedido_id"]
            if resultado.get("codigo_entrega"):
                texto = (
                    f"¡Perfecto! Tu pedido a domicilio quedó registrado con el número {numero}. El restaurante lo "
                    f"confirmará en breve. Cuando llegue el domiciliario, dale este código: {self._codigo(resultado['codigo_entrega'])}. "
                    "Muchas gracias por comprar con nosotros."
                )
            elif resultado["aviso_cocina"]:
                texto = (
                    f"¡Perfecto! Tu pedido quedó registrado con el número {numero}. El restaurante lo confirmará "
                    "en breve y pasará a cocina. Muchas gracias por comprar con nosotros."
                )
            else:
                texto = (
                    f"Tu pedido quedó registrado con el número {numero}. El restaurante lo verá en su lista de "
                    "pedidos por confirmar. Muchas gracias por comprar con nosotros."
                )
            return Respuesta(texto, finalizar=True)
        if resultado["error"] == "PRODUCTO_NO_DISPONIBLE":
            self._ir_a(Llamada.FASE_PEDIDO)
            self._depurar_no_disponibles()
            return Respuesta(
                "Uno de los productos dejó de estar disponible y lo quité del pedido. "
                "¿Quieres cambiarlo por otro o confirmo lo demás?"
            )
        return self._siguiente_paso()

    def _depurar_no_disponibles(self):
        for producto_id, cantidad in list(self.llamada.items.items()):
            if not self.herramientas.consultar_disponibilidad(int(producto_id), cantidad)["disponible"]:
                self.herramientas.eliminar_producto_borrador(int(producto_id))

    def _en_datos_registrados(self, intencion):
        if intencion.productos:
            return None
        if intencion.afirma and not intencion.niega:
            cliente = self.herramientas.consultar_cliente(self.llamada.telefono_origen)
            if cliente:
                self.llamada.nombre_cliente = cliente["nombre"]
                self.llamada.cliente_id = cliente["id"]
                self._guardar("nombre_cliente", "cliente")
            return self._siguiente_paso()
        if intencion.niega:
            self._ir_a(Llamada.FASE_NOMBRE)
            return Respuesta("Entendido. ¿A nombre de quién dejo el pedido?")
        return Respuesta("¿El pedido va a ese nombre? Responde sí o no, por favor.")

    def _codigo(self, codigo):
        return " ".join(codigo) if self.llamada.canal == Llamada.CANAL_TELEFONO else codigo

    def _nombre_de(self, intencion):
        palabras = re.sub(r"[^\w\s'-]", " ", PREFIJO_NOMBRE.sub("", intencion.texto)).split()
        if intencion.nombre:
            palabras = palabras[:len(intencion.nombre.split())]
        if not 1 <= len(palabras) <= 4 or any(p.isdigit() for p in palabras):
            return ""
        return " ".join(p.capitalize() for p in palabras)[:150]

    def _en_nombre(self, intencion):
        if intencion.productos and not intencion.nombre:
            return None
        if not intencion.nombre and (intencion.afirma or intencion.niega or intencion.modalidad):
            return Respuesta("Necesito un nombre para el pedido. ¿A nombre de quién lo dejo?")
        nombre = self._nombre_de(intencion)
        if not nombre:
            return Respuesta("No te entendí el nombre. ¿Me lo repites, por favor?")
        self.llamada.nombre_cliente = nombre
        self._guardar("nombre_cliente")
        return self._siguiente_paso()

    def _en_telefono(self, intencion):
        telefono = extraer_telefono(intencion.normal)
        if not telefono:
            if intencion.productos:
                return None
            return Respuesta("No entendí el número. ¿Me lo dices dígito por dígito, por favor?")
        self.llamada.telefono_contacto = telefono
        self._guardar("telefono_contacto")
        return self._siguiente_paso()

    def _en_modalidad(self, intencion):
        if intencion.modalidad:
            self.llamada.tipo_consumo = intencion.modalidad
            self.llamada.resumen_leido = False
            self._guardar("tipo_consumo", "resumen_leido")
            if not self.llamada.items:
                self._ir_a(Llamada.FASE_PEDIDO)
                return Respuesta("Claro. ¿Qué te gustaría ordenar?")
            return self._siguiente_paso()
        if intencion.productos:
            return None
        return Respuesta(PREGUNTA_MODALIDAD)

    def _en_direccion(self, intencion):
        direccion = intencion.texto.strip()
        if len(direccion) < LARGO_MINIMO_DIRECCION:
            return Respuesta(f"No entendí la dirección. {self._pregunta_direccion()}")
        self.llamada.direccion = direccion[:255]
        self.llamada.resumen_leido = False
        self._guardar("direccion", "resumen_leido")
        return self._siguiente_paso()

    def _en_referencia(self, intencion):
        datos = dict(self.llamada.datos)
        datos["referencia_preguntada"] = True
        self.llamada.datos = datos
        negativa = intencion.niega or contiene(intencion.normal, "ninguna", "ninguno", "nada")
        self.llamada.referencia = "" if negativa else intencion.texto.strip()[:255]
        self.llamada.resumen_leido = False
        self._guardar("datos", "referencia", "resumen_leido")
        return self._siguiente_paso()

    def _pregunta_direccion(self):
        if self.llamada.canal == Llamada.CANAL_WHATSAPP:
            return "¿Cuál es la dirección de entrega? También puedes compartir tu ubicación por WhatsApp."
        return "¿Cuál es la dirección de entrega?"

    def _siguiente_paso(self):
        llamada = self.llamada
        if not llamada.items:
            self._ir_a(Llamada.FASE_PEDIDO)
            return Respuesta("Todavía no tienes productos en el pedido. ¿Qué te gustaría ordenar?")
        if not llamada.nombre_cliente:
            if not llamada.datos_registrados_ofrecidos:
                llamada.datos_registrados_ofrecidos = True
                self._guardar("datos_registrados_ofrecidos")
                cliente = self.herramientas.consultar_cliente(llamada.telefono_origen)
                if cliente:
                    self._ir_a(Llamada.FASE_DATOS_REGISTRADOS)
                    return Respuesta(
                        f"Tengo un cliente registrado con este número a nombre de {cliente['nombre']}. "
                        "¿El pedido va a ese nombre?"
                    )
            self._ir_a(Llamada.FASE_NOMBRE)
            return Respuesta("¿A nombre de quién dejo el pedido?")
        if not llamada.telefono_contacto:
            self._ir_a(Llamada.FASE_TELEFONO)
            return Respuesta("¿A qué número de teléfono te podemos contactar?")
        if not llamada.tipo_consumo:
            self._ir_a(Llamada.FASE_MODALIDAD)
            return Respuesta(PREGUNTA_MODALIDAD)
        if llamada.tipo_consumo == Orden.DOMICILIO:
            if not llamada.direccion and llamada.latitud is not None:
                llamada.direccion = DIRECCION_POR_UBICACION
                self._guardar("direccion")
            if not llamada.direccion:
                self._ir_a(Llamada.FASE_DIRECCION)
                return Respuesta(self._pregunta_direccion())
            if not llamada.datos.get("referencia_preguntada"):
                self._ir_a(Llamada.FASE_REFERENCIA)
                return Respuesta("¿Alguna referencia para encontrarte, como barrio, torre o apartamento? Si no, dime no.")
        return self._leer_resumen()

    def _leer_resumen(self):
        total = self.herramientas.calcular_total_pedido()
        partes = [
            f"{_cantidad_texto(l['cantidad'])} {l['nombre']} a {formatear_pesos(l['precio_unitario'])}"
            + (" cada uno" if l["cantidad"] > 1 else "")
            for l in total["lineas"]
        ]
        cargos = total["impuestos"] + total["cargos"]
        texto_cargos = (
            f"Impuestos y cargos: {formatear_pesos(cargos)}. " if cargos else "No tiene impuestos ni cargos adicionales. "
        )
        if self.llamada.tipo_consumo == Orden.DOMICILIO:
            referencia = f", {self.llamada.referencia}" if self.llamada.referencia else ""
            modalidad = f"a domicilio en {self.llamada.direccion}{referencia}"
        elif self.llamada.tipo_consumo == Orden.PARA_LLEVAR:
            modalidad = "para recoger en el restaurante"
        else:
            modalidad = "para comer en el restaurante"
        texto = (
            f"Tu pedido a nombre de {self.llamada.nombre_cliente} contiene {_lista(partes)}. "
            f"Subtotal: {formatear_pesos(total['subtotal'])}. {texto_cargos}"
            f"El total es de {formatear_pesos(total['total'])}, {modalidad}. "
        )
        if self.llamada.observaciones:
            texto += f"Observaciones: {self.llamada.observaciones}. "
        texto += f"Teléfono de contacto terminado en {ultimos_digitos(self.llamada.telefono_contacto, 4)}. "
        texto += "¿Confirmas que deseas realizar este pedido?"
        self.llamada.resumen_leido = True
        self.llamada.fase = Llamada.FASE_CONFIRMACION
        self._guardar("resumen_leido", "fase")
        return Respuesta(texto)

    def _general(self, intencion):
        tipo = intencion.tipo
        if self.llamada.fase == Llamada.FASE_CONFIRMACION:
            self._ir_a(Llamada.FASE_PEDIDO)
        if tipo == "RESERVA":
            return self._iniciar_reserva(intencion)
        if tipo == "AGREGAR":
            return self._agregar(intencion)
        if tipo == "ELIMINAR":
            return self._eliminar(intencion)
        if tipo == "MODIFICAR":
            return self._modificar(intencion)
        if tipo == "PRECIO":
            return self._precio(intencion)
        if tipo == "INGREDIENTES":
            return self._ingredientes(intencion)
        if tipo == "SUBTOTAL":
            return self._subtotal()
        if tipo == "MENU":
            return self._menu(intencion.categoria)
        if tipo == "ECONOMICOS":
            return self._economicos()
        if tipo == "AGOTADOS":
            return self._agotados()
        if tipo == "OBSERVACION":
            self.herramientas.agregar_observacion(intencion.observacion)
            return Respuesta(f"Anoté la observación: {intencion.observacion}. ¿Algo más?")
        if tipo == "MODALIDAD":
            return self._en_modalidad(intencion)
        if tipo == "NOMBRE":
            return self._en_nombre(intencion)
        if tipo == "SALUDO":
            return Respuesta("¡Hola! ¿Qué te gustaría ordenar?")
        if tipo == "MANIPULACION":
            return Respuesta("¿Qué te gustaría ordenar?")
        if tipo in ("FIN", "NEGAR"):
            if not self.llamada.items:
                self._cerrar(Llamada.FINALIZADA)
                return Respuesta("Entendido. Gracias por llamar. ¡Que tengas un buen día!", finalizar=True)
            return self._siguiente_paso()
        if tipo == "AFIRMAR":
            if self.llamada.items:
                return Respuesta("Claro, ¿qué más te gustaría agregar? Si eso es todo, dime «eso es todo».")
            return Respuesta("¡Con gusto! ¿Qué te gustaría ordenar?")
        if intencion.no_encontrados:
            return Respuesta(
                f"No encontré «{intencion.no_encontrados[0]}» en nuestro menú. "
                "¿Quieres que te diga qué tenemos disponible?"
            )
        return Respuesta(
            "No te entendí bien. Puedes pedirme un plato del menú, preguntarme precios o decir «eso es todo» para terminar."
        )

    def _iniciar_reserva(self, intencion):
        if contiene(intencion.normal, "cancela", "cancelar", "cancelalo", "anula", "anular", "cambiar", "cambia"):
            return Respuesta("Para cambiar o cancelar una reserva comunícate con el restaurante. ¿Te ayudo con algo más?")
        if self.llamada.items:
            return Respuesta("Primero terminemos tu pedido. Di «eso es todo» para seguir o «cancelar» para empezar la reserva.")
        self.llamada.datos = {}
        self._guardar("datos")
        self._capturar_reserva(intencion)
        return self._siguiente_reserva()

    def _capturar_reserva(self, intencion):
        normal, fase = intencion.normal, self.llamada.fase
        hora = extraer_hora(normal)
        if hora is None and fase == Llamada.FASE_RESERVA_HORA:
            hora = extraer_hora_suelta(normal)
        personas = extraer_personas(normal)
        if personas is None and fase == Llamada.FASE_RESERVA_PERSONAS:
            personas, _ = extraer_cantidad(normal.split())
        fecha = extraer_fecha(normal, timezone.localdate())
        nuevos = {
            "fecha": fecha.isoformat() if fecha else None,
            "hora": f"{hora[0]:02d}:{hora[1]:02d}" if hora else None,
            "personas": personas,
        }
        nuevos = {clave: valor for clave, valor in nuevos.items() if valor}
        if intencion.nombre and fase != Llamada.FASE_RESERVA_NOMBRE:
            self.llamada.nombre_cliente = " ".join(p.capitalize() for p in intencion.nombre.split())[:150]
            self._guardar("nombre_cliente")
        if not nuevos:
            return False
        self.llamada.datos = {**self.llamada.datos, **nuevos, "resumen_leido": False}
        self._guardar("datos")
        return True

    def _en_reserva(self, intencion):
        fase = self.llamada.fase
        entendido = self._capturar_reserva(intencion)
        if fase == Llamada.FASE_RESERVA_NOMBRE:
            nombre = self._nombre_de(intencion)
            if nombre:
                self.llamada.nombre_cliente = nombre
                self._guardar("nombre_cliente")
                entendido = True
        if fase == Llamada.FASE_RESERVA_TELEFONO:
            telefono = extraer_telefono(intencion.normal)
            if telefono:
                self.llamada.telefono_contacto = telefono
                self._guardar("telefono_contacto")
                entendido = True
        if fase == Llamada.FASE_RESERVA_CONFIRMACION and not entendido:
            if intencion.niega and not intencion.afirma:
                return Respuesta("De acuerdo, todavía no la registro. Dime el nuevo día, hora o número de personas, o di cancelar.")
            if intencion.afirma:
                return self._confirmar_reserva()
            return Respuesta("Para registrarla necesito que me digas sí o no. ¿Confirmas la reserva?")
        respuesta = self._siguiente_reserva()
        if not entendido:
            respuesta.texto = "No te entendí bien. " + respuesta.texto
        return respuesta

    def _siguiente_reserva(self):
        datos, llamada = self.llamada.datos, self.llamada
        pasos = (
            (datos.get("fecha"), Llamada.FASE_RESERVA_FECHA, "¿Para qué día quieres la reserva?"),
            (datos.get("hora"), Llamada.FASE_RESERVA_HORA, "¿A qué hora?"),
            (datos.get("personas"), Llamada.FASE_RESERVA_PERSONAS, "¿Para cuántas personas?"),
            (llamada.nombre_cliente, Llamada.FASE_RESERVA_NOMBRE, "¿A nombre de quién dejo la reserva?"),
            (llamada.telefono_contacto, Llamada.FASE_RESERVA_TELEFONO, "¿A qué número de teléfono te podemos contactar?"),
        )
        for valor, fase, pregunta in pasos:
            if not valor:
                self._ir_a(fase)
                return Respuesta(pregunta)
        return self._leer_resumen_reserva()

    def _leer_resumen_reserva(self):
        datos = self.llamada.datos
        hora, minuto = (int(parte) for parte in datos["hora"].split(":"))
        dia = date_format(date.fromisoformat(datos["fecha"]), "l j \\d\\e F")
        self.llamada.datos = {**datos, "resumen_leido": True}
        self.llamada.fase = Llamada.FASE_RESERVA_CONFIRMACION
        self._guardar("datos", "fase")
        personas = "1 persona" if datos["personas"] == 1 else f"{datos['personas']} personas"
        return Respuesta(
            f"Tu reserva es para {personas} el {dia} a las {_hora_texto(hora, minuto)}, "
            f"a nombre de {self.llamada.nombre_cliente}. ¿Confirmas la reserva?"
        )

    def _quitar_de_reserva(self, *claves):
        self.llamada.datos = {k: v for k, v in self.llamada.datos.items() if k not in claves}
        self._guardar("datos")

    def _confirmar_reserva(self):
        resultado = self.herramientas.confirmar_reserva(True)
        self.llamada = self.herramientas.llamada
        if resultado["ok"]:
            self._cerrar(Llamada.FINALIZADA)
            return Respuesta(
                f"¡Listo! Tu reserva quedó confirmada. Tu código es {self._codigo(resultado['codigo'])}. "
                "Muéstralo o díselo al mesero cuando llegues. ¡Te esperamos!",
                finalizar=True,
            )
        error = resultado["error"]
        if error == "sin_mesa":
            self._quitar_de_reserva("hora", "resumen_leido")
            self._ir_a(Llamada.FASE_RESERVA_HORA)
            horas = [_hora_texto(a.hour, a.minute) for a in resultado.get("alternativas", [])]
            if horas:
                return Respuesta(f"A esa hora no tenemos mesas. Tengo disponible a las {_lista(horas)}. ¿Cuál prefieres?")
            return Respuesta("A esa hora no tenemos mesas. ¿Quieres probar con otra hora?")
        if error in ("anticipacion", "horizonte"):
            self._quitar_de_reserva("fecha", "hora", "resumen_leido")
            self._ir_a(Llamada.FASE_RESERVA_FECHA)
            return Respuesta(f"{resultado['detalle']} ¿Para qué día quieres la reserva?")
        if error in ("capacidad", "personas"):
            self._quitar_de_reserva("personas", "resumen_leido")
            self._ir_a(Llamada.FASE_RESERVA_PERSONAS)
            return Respuesta(f"{resultado['detalle']} ¿Para cuántas personas?")
        return Respuesta("No pude registrar la reserva. ¿Quieres intentarlo de nuevo? Dime sí o no.")

    def _resolver(self, intencion):
        resueltos, ambiguos = [], []
        pendiente = self.llamada.pendiente.get("opciones")
        for busqueda, cantidad in intencion.productos:
            if busqueda["estado"] == "AMBIGUO":
                opciones = busqueda["opciones"]
                if pendiente:
                    elegidas = [o for o in opciones if o["id"] in pendiente]
                    if len(elegidas) == 1:
                        resueltos.append((elegidas[0], cantidad or self.llamada.pendiente.get("cantidad")))
                        continue
                ambiguos.append((opciones, cantidad))
            else:
                producto = busqueda["producto"]
                if pendiente and producto["id"] in pendiente and not cantidad:
                    cantidad = self.llamada.pendiente.get("cantidad")
                resueltos.append((producto, cantidad))
        return resueltos, ambiguos

    def _preguntar_ambiguo(self, opciones, cantidad):
        self.llamada.pendiente = {"opciones": [o["id"] for o in opciones], "cantidad": cantidad}
        self._guardar("pendiente")
        nombres = [o["nombre"] for o in opciones]
        return f"¿Cuál prefieres: {', '.join(nombres[:-1])} o {nombres[-1]}?"

    def _agregar(self, intencion):
        resueltos, ambiguos = self._resolver(intencion)
        if self.llamada.pendiente:
            self.llamada.pendiente = {}
            self._guardar("pendiente")
        agregados, rechazados = [], []
        for producto, cantidad in resueltos:
            cantidad = cantidad or 1
            resultado = self.herramientas.agregar_producto_borrador(producto["id"], cantidad)
            if resultado["ok"]:
                agregados.append(f"{_cantidad_texto(cantidad)} {producto['nombre']}")
            else:
                rechazados.append(f"{producto['nombre']} {MOTIVOS_NO_AGREGADO.get(resultado['error'], 'no se pudo agregar')}")
        if intencion.observacion:
            self.herramientas.agregar_observacion(intencion.observacion)
        if intencion.modalidad in (Orden.PARA_LLEVAR, Orden.EN_RESTAURANTE, Orden.DOMICILIO):
            self.llamada.tipo_consumo = intencion.modalidad
            self._guardar("tipo_consumo")
        texto = ""
        if agregados:
            texto += f"Perfecto. Agregué {_lista(agregados)}. "
        if rechazados:
            texto += f"Lo siento, {_lista(rechazados)}. "
        if intencion.no_encontrados:
            texto += f"No encontré «{intencion.no_encontrados[0]}» en el menú. "
        if ambiguos:
            return Respuesta(texto + self._preguntar_ambiguo(*ambiguos[0]))
        if agregados or rechazados:
            texto += "¿Deseas agregar algo más?"
        return Respuesta(texto.strip())

    def _en_pedido(self, intencion):
        resueltos, ambiguos = self._resolver(intencion)
        if ambiguos:
            return None, Respuesta(self._preguntar_ambiguo(*ambiguos[0]))
        return resueltos, None

    def _eliminar(self, intencion):
        resueltos, respuesta = self._en_pedido(intencion)
        if respuesta:
            return respuesta
        quitados = [p["nombre"] for p, _ in resueltos if self.herramientas.eliminar_producto_borrador(p["id"])["ok"]]
        if not quitados:
            return Respuesta("Ese producto no estaba en tu pedido. ¿Algo más?")
        restante = "" if self.llamada.items else " Tu pedido quedó vacío."
        return Respuesta(f"Listo, quité {_lista(quitados)}.{restante} ¿Algo más?")

    def _modificar(self, intencion):
        resueltos, respuesta = self._en_pedido(intencion)
        if respuesta:
            return respuesta
        cambios, errores = [], []
        for producto, cantidad in resueltos:
            if not cantidad:
                continue
            resultado = self.herramientas.modificar_producto_borrador(producto["id"], cantidad)
            if resultado["ok"]:
                cambios.append(f"{_cantidad_texto(cantidad)} {producto['nombre']}")
            elif resultado["error"] == "NO_EN_PEDIDO":
                agregado = self.herramientas.agregar_producto_borrador(producto["id"], cantidad)
                if agregado["ok"]:
                    cambios.append(f"{_cantidad_texto(cantidad)} {producto['nombre']}")
                else:
                    errores.append(f"{producto['nombre']} {MOTIVOS_NO_AGREGADO.get(agregado['error'], 'no se pudo cambiar')}")
            else:
                errores.append(f"{producto['nombre']} {MOTIVOS_NO_AGREGADO.get(resultado['error'], 'no se pudo cambiar')}")
        texto = f"Listo, ahora tienes {_lista(cambios)}. " if cambios else ""
        if errores:
            texto += f"Lo siento, {_lista(errores)}. "
        return Respuesta((texto or "No identifiqué la cantidad. ") + "¿Algo más?")

    def _precio(self, intencion):
        resueltos, respuesta = self._en_pedido(intencion)
        if respuesta:
            return respuesta
        partes = []
        for producto, _ in resueltos:
            estado = "" if producto["disponible"] else ", aunque ahora no está disponible"
            partes.append(f"{producto['nombre']} cuesta {formatear_pesos(producto['precio'])}{estado}")
        return Respuesta(f"{_lista(partes)}. ¿Te lo agrego?")

    def _ingredientes(self, intencion):
        resueltos, respuesta = self._en_pedido(intencion)
        if respuesta:
            return respuesta
        producto = resueltos[0][0]
        ingredientes = self.herramientas.ingredientes(producto["id"])
        if ingredientes:
            return Respuesta(f"{producto['nombre']} lleva {_lista(ingredientes)}. ¿Te lo agrego?")
        if producto["descripcion"]:
            return Respuesta(f"{producto['nombre']}: {producto['descripcion']}. ¿Te lo agrego?")
        return Respuesta(f"No tengo registrados los ingredientes de {producto['nombre']}. ¿Te ayudo con algo más?")

    def _subtotal(self):
        total = self.herramientas.calcular_total_pedido()
        if not total["lineas"]:
            return Respuesta("Todavía no tienes productos en el pedido. ¿Qué te gustaría ordenar?")
        return Respuesta(f"Hasta ahora tu pedido suma {formatear_pesos(total['total'])}. ¿Deseas agregar algo más?")

    def _menu(self, categoria=""):
        productos = self.herramientas.consultar_menu(categoria or None)
        if not productos:
            return Respuesta("En este momento no tenemos productos disponibles en esa categoría.")
        if not categoria and len(productos) > MAX_PRODUCTOS_LEIDOS:
            return Respuesta(
                f"Tenemos {_lista(self.herramientas.categorias())}. ¿De cuál categoría te cuento?"
            )
        partes = [f"{p['nombre']} a {formatear_pesos(p['precio'])}" for p in productos[:MAX_PRODUCTOS_LEIDOS]]
        return Respuesta(f"Tenemos {_lista(partes)}. ¿Qué te gustaría pedir?")

    def _economicos(self):
        productos = sorted(self.herramientas.consultar_menu(), key=lambda p: p["precio"])[:3]
        if not productos:
            return Respuesta("En este momento no tenemos productos disponibles.")
        partes = [f"{p['nombre']} a {formatear_pesos(p['precio'])}" for p in productos]
        return Respuesta(f"Las opciones más económicas son {_lista(partes)}. ¿Te agrego alguna?")

    def _agotados(self):
        agotados = self.herramientas.productos_agotados()
        if not agotados:
            return Respuesta("Ahora mismo tenemos todo el menú disponible. ¿Qué te gustaría ordenar?")
        return Respuesta(f"En este momento no tenemos {_lista([p['nombre'] for p in agotados])}. ¿Qué más te gustaría?")
