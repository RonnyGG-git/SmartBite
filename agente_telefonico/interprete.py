import re
from dataclasses import dataclass, field

from .texto import (
    PALABRAS_VACIAS,
    contiene,
    extraer_cantidad,
    extraer_numero_pedido,
    forma_canonica,
    normalizar,
)

AFIRMATIVAS = (
    "si", "sip", "claro", "confirmo", "correcto", "dale", "de una", "ok", "okay", "vale", "exacto",
    "perfecto", "asi es", "confirmar", "hagale", "por supuesto", "afirmativo", "esta bien", "listo", "bueno",
)
NEGATIVAS = ("no", "nop", "negativo", "incorrecto", "todavia no", "aun no", "espera", "esperame")
FIN_PEDIDO = (
    "nada mas", "eso es todo", "es todo", "seria todo", "solo eso", "no mas", "ya esta", "eso seria",
    "eso es", "nada", "listo", "ya", "no gracias",
)
HUMANO = ("operador", "operadora", "asesor", "asesora", "persona", "humano", "hablar con alguien", "alguien real")
CANCELAR = ("cancela", "cancelar", "cancelalo", "ya no quiero", "olvidalo", "olvida", "anula", "anular")
QUITAR = (
    "quita", "quitale", "quitar", "quitame", "elimina", "eliminar", "eliminame", "saca", "sacale", "sacame",
    "borra", "borrar", "remueve", "cancela", "cancelar", "ya no quiero",
)
MODIFICAR = ("cambia", "cambiar", "cambiame", "que sean", "mejor", "solo", "modifica", "deja", "dejalo en", "ponle", "en vez de")
MENU = (
    "menu", "carta", "que tienen", "que hay", "que venden", "que ofrecen", "opciones", "que platos",
    "que platillos", "que me recomiendas", "que tienes", "productos", "disponible", "disponibles",
)
ECONOMICOS = ("mas barato", "mas barata", "mas baratos", "mas baratas", "mas economico", "mas economica", "mas economicos", "mas economicas")
AGOTADOS = ("agotado", "agotados", "agotada", "agotadas", "no hay", "no tienen", "no tienes")
PRECIO = ("cuanto cuesta", "cuanto vale", "cuanto valen", "cuanto cuestan", "precio", "que precio", "a como")
SUBTOTAL = ("cuanto va", "cuanto llevo", "cuanto es", "subtotal", "total", "cuanto seria", "cuanto me sale", "cuanto queda")
INGREDIENTES = ("ingrediente", "ingredientes", "que trae", "que lleva", "que tiene", "de que es", "que contiene")
ESTADO = ("estado", "como va mi pedido", "como va el pedido", "ya esta listo mi pedido", "mi pedido")
OBSERVACION = ("observacion", "nota", "comentario", "bien asado", "bien asada", "termino medio", "aparte")
PARA_LLEVAR = ("recoger", "recojo", "recogerlo", "recogerla", "paso por", "para llevar", "lo recojo", "voy por", "llevar")
EN_LOCAL = (
    "comer alla", "comer aca", "comer aqui", "en el local", "comer en el restaurante", "alla mismo",
    "en el sitio", "comerlo alla", "comer en el local", "consumir alla", "consumir en el local",
)
DOMICILIO = ("domicilio", "a domicilio", "me lo traen", "envio", "delivery", "a mi casa", "me lo mandan", "me lo envian")
MANIPULACION = (
    "gratis", "descuento", "rebaja", "regalado", "cobrame", "cobra", "precio es", "cuesta solo", "ignora",
    "instrucciones", "modo desarrollador", "mitad de precio", "sin costo", "no me cobres", "cambia el precio",
)
PATRON_NOMBRE = re.compile(r"(?:me llamo|mi nombre es|a nombre de|soy)\s+([a-z]+(?: [a-z]+){0,2}?)(?=\s+y\s|\s+quiero|,|$)")
PATRON_OBSERVACION = re.compile(r"\b(sin [a-z ]+?|con extra de [a-z ]+?|bien asad[oa]|termino medio)(?=\s+y\s|,|$)")
PATRON_MONTO = re.compile(r"\b\d+\s*(?:mil|pesos|lucas)\b|\bmil pesos\b")
SALUDOS = {"hola", "buenas", "buenos", "dias", "tardes", "noches", "alo", "quiubo", "que", "tal", "buen", "dia"}
SEPARADORES = re.compile(r"\s*(?:,|\by\b|\bmas\b|\btambien\b|\bademas\b)\s*")

RUIDO = PALABRAS_VACIAS | {
    palabra
    for frases in (AFIRMATIVAS, NEGATIVAS, QUITAR, MODIFICAR, PRECIO, INGREDIENTES, SUBTOTAL, MENU, PARA_LLEVAR,
                   EN_LOCAL, ECONOMICOS, CANCELAR, ("cuanto", "cuesta", "vale", "valen", "porfavor", "hola", "buenas",
                                                  "buenos", "dias", "tardes", "noches", "gracias", "pedido", "orden"))
    for frase in frases
    for palabra in frase.split()
}


@dataclass
class Intencion:
    tipo: str
    texto: str
    normal: str
    productos: list = field(default_factory=list)
    no_encontrados: list = field(default_factory=list)
    afirma: bool = False
    niega: bool = False
    fin: bool = False
    sospecha_precio: bool = False
    numero: int | None = None
    modalidad: str = ""
    nombre: str = ""
    observacion: str = ""
    categoria: str = ""


def _limpiar_consulta(segmento):
    palabras = segmento.split()
    cantidad, indice = extraer_cantidad(palabras)
    resto = [p for i, p in enumerate(palabras) if i != indice and p not in RUIDO and not p.isdigit()]
    return cantidad, " ".join(resto)


def _buscar_productos(normal, herramientas):
    encontrados, no_encontrados = [], []
    sin_observaciones = PATRON_OBSERVACION.sub(" ", normal)
    for segmento in SEPARADORES.split(sin_observaciones):
        cantidad, consulta = _limpiar_consulta(segmento.strip())
        if not consulta:
            continue
        resultado = herramientas.buscar_producto(consulta)
        if resultado["estado"] == "NO_ENCONTRADO":
            no_encontrados.append(consulta)
        else:
            encontrados.append((resultado, cantidad))
    return encontrados, no_encontrados


def _categoria(normal, herramientas):
    canonico = f" {forma_canonica(normal)} "
    for nombre in herramientas.categorias():
        if f" {forma_canonica(nombre)} " in canonico:
            return nombre
    return ""


def interpretar(texto, herramientas):
    normal = normalizar(texto)
    intencion = Intencion(tipo="DESCONOCIDO", texto=texto or "", normal=normal)
    if not normal:
        intencion.tipo = "VACIO"
        return intencion

    if set(normal.split()) <= SALUDOS:
        intencion.tipo = "SALUDO"
        return intencion

    intencion.afirma = contiene(normal, *AFIRMATIVAS)
    intencion.niega = contiene(normal, *NEGATIVAS)
    intencion.fin = contiene(normal, *FIN_PEDIDO)
    intencion.sospecha_precio = contiene(normal, *MANIPULACION) or bool(PATRON_MONTO.search(normal))
    intencion.numero = extraer_numero_pedido(normal)
    intencion.categoria = _categoria(normal, herramientas)
    if contiene(normal, *DOMICILIO):
        intencion.modalidad = "DOMICILIO"
    elif contiene(normal, *EN_LOCAL):
        intencion.modalidad = "EN_RESTAURANTE"
    elif contiene(normal, *PARA_LLEVAR):
        intencion.modalidad = "PARA_LLEVAR"
    coincidencia = PATRON_NOMBRE.search(normal)
    if coincidencia:
        intencion.nombre = coincidencia.group(1).strip()
    observacion = PATRON_OBSERVACION.search(normal)
    if observacion:
        intencion.observacion = observacion.group(1).strip()

    if contiene(normal, *HUMANO):
        intencion.tipo = "HUMANO"
        return intencion
    if contiene(normal, *ESTADO) or (intencion.numero and contiene(normal, "pedido", "orden")):
        intencion.tipo = "ESTADO"
        return intencion

    sin_nombre = PATRON_NOMBRE.sub(" ", normal) if intencion.nombre else normal
    intencion.productos, intencion.no_encontrados = _buscar_productos(sin_nombre, herramientas)
    tiene_productos = bool(intencion.productos)

    if contiene(normal, *QUITAR) and tiene_productos:
        intencion.tipo = "ELIMINAR"
    elif contiene(normal, *CANCELAR) and not tiene_productos:
        intencion.tipo = "CANCELAR"
    elif contiene(normal, *PRECIO) and tiene_productos:
        intencion.tipo = "PRECIO"
    elif contiene(normal, *INGREDIENTES) and tiene_productos:
        intencion.tipo = "INGREDIENTES"
    elif contiene(normal, *MODIFICAR) and tiene_productos and any(c for _, c in intencion.productos):
        intencion.tipo = "MODIFICAR"
    elif contiene(normal, *SUBTOTAL) and not tiene_productos:
        intencion.tipo = "SUBTOTAL"
    elif contiene(normal, *ECONOMICOS):
        intencion.tipo = "ECONOMICOS"
    elif contiene(normal, *AGOTADOS) and not tiene_productos:
        intencion.tipo = "AGOTADOS"
    elif contiene(normal, *MENU) and not tiene_productos:
        intencion.tipo = "MENU"
    elif tiene_productos:
        intencion.tipo = "AGREGAR"
    elif intencion.modalidad:
        intencion.tipo = "MODALIDAD"
    elif intencion.nombre:
        intencion.tipo = "NOMBRE"
    elif intencion.observacion or contiene(normal, *OBSERVACION):
        intencion.tipo = "OBSERVACION"
        intencion.observacion = intencion.observacion or (texto or "").strip()[:150]
    elif intencion.categoria:
        intencion.tipo = "MENU"
    elif intencion.sospecha_precio:
        intencion.tipo = "MANIPULACION"
    elif intencion.fin:
        intencion.tipo = "FIN"
    elif intencion.afirma:
        intencion.tipo = "AFIRMAR"
    elif intencion.niega:
        intencion.tipo = "NEGAR"
    return intencion
