import re
import unicodedata
from datetime import date, timedelta

NUMEROS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "veinte": 20, "par": 2, "docena": 12,
}

PALABRAS_VACIAS = {
    "quiero", "quisiera", "me", "da", "das", "dame", "regalas", "regala", "porfa", "por", "favor",
    "tambien", "y", "con", "de", "del", "el", "la", "los", "las", "unos", "unas", "agrega", "agregame",
    "anade", "pon", "ponme", "mas", "otro", "otra", "seria", "sería", "pedir", "para", "mi", "un", "una",
    "deme", "traeme", "manda", "mandame", "que", "sean", "mejor", "cambia", "solo", "nada",
}

TARJETA = re.compile(r"(?:\d[ -]?){13,19}")

DIAS_SEMANA = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
PALABRAS_NUMERO = "|".join(sorted((p for p in NUMEROS if p not in ("par", "docena")), key=len, reverse=True))
NUMERO = rf"\d{{1,2}}|{PALABRAS_NUMERO}"
PATRON_MANANA_DIA = re.compile(r"(?<!la )\bmanana\b")
PATRON_DIA_MES = re.compile(rf"\b({NUMERO})\s+de\s+({'|'.join(MESES)})\b")
PATRON_EL_DIA = re.compile(r"\bel\s+(\d{1,2})\b(?!\s+personas?)")
PATRON_HORA = re.compile(rf"\b(?:a\s+las?|las?)\s+({NUMERO})(?:\s+(?:y\s+)?(media|cuarto|\d{{2}}))?\b(?!\s+personas?)")
PATRON_HORA_AMPM = re.compile(r"\b(\d{1,2})(?:\s+(\d{2}))?\s*(am|pm|a m|p m)\b")
PATRON_HORA_SUELTA = re.compile(r"^(\d{1,2})(?:\s+(\d{2}))?$")
PATRON_PERSONAS = re.compile(rf"\b(?:({NUMERO})\s+personas?|somos\s+({NUMERO})|mesa\s+para\s+({NUMERO}))\b")
TARDE = ("de la tarde", "de la noche", "por la tarde", "por la noche", "en la tarde", "en la noche", "esta tarde", "esta noche")
MANANA = ("de la manana", "por la manana", "en la manana")


def _a_numero(texto):
    return int(texto) if texto.isdigit() else NUMEROS.get(texto)


def _fecha_valida(anio, mes, dia):
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def extraer_fecha(texto_normal, hoy):
    if contiene(texto_normal, "pasado manana"):
        return hoy + timedelta(days=2)
    if contiene(texto_normal, "hoy", "esta noche", "esta tarde"):
        return hoy
    if PATRON_MANANA_DIA.search(texto_normal):
        return hoy + timedelta(days=1)
    for nombre, indice in DIAS_SEMANA.items():
        if contiene(texto_normal, nombre):
            return hoy + timedelta(days=(indice - hoy.weekday()) % 7 or 7)
    coincidencia = PATRON_DIA_MES.search(texto_normal)
    if coincidencia:
        dia, mes = _a_numero(coincidencia.group(1)), MESES[coincidencia.group(2)]
        fecha = _fecha_valida(hoy.year, mes, dia)
        return fecha if fecha is None or fecha >= hoy else _fecha_valida(hoy.year + 1, mes, dia)
    coincidencia = PATRON_EL_DIA.search(texto_normal)
    if coincidencia:
        dia = int(coincidencia.group(1))
        fecha = _fecha_valida(hoy.year, hoy.month, dia)
        if fecha is not None and fecha >= hoy:
            return fecha
        siguiente = date(hoy.year + hoy.month // 12, hoy.month % 12 + 1, 1)
        return _fecha_valida(siguiente.year, siguiente.month, dia)
    return None


def _minutos(texto):
    if not texto:
        return 0
    if texto == "media":
        return 30
    if texto == "cuarto":
        return 15
    return int(texto)


def _a_24_horas(hora, minuto, texto_normal, sufijo=""):
    if hora is None or hora > 23 or minuto > 59:
        return None
    if sufijo.startswith("p") or contiene(texto_normal, *TARDE):
        hora += 12 if hora < 12 else 0
    elif sufijo.startswith("a") or contiene(texto_normal, *MANANA):
        hora = 0 if hora == 12 else hora
    elif 1 <= hora <= 11:
        hora += 12
    return hora, minuto


def extraer_hora(texto_normal):
    if contiene(texto_normal, "mediodia", "medio dia"):
        return 12, 0
    coincidencia = PATRON_HORA_AMPM.search(texto_normal)
    if coincidencia:
        return _a_24_horas(int(coincidencia.group(1)), int(coincidencia.group(2) or 0), texto_normal, coincidencia.group(3))
    coincidencia = PATRON_HORA.search(texto_normal)
    if coincidencia:
        return _a_24_horas(_a_numero(coincidencia.group(1)), _minutos(coincidencia.group(2)), texto_normal)
    return None


def extraer_hora_suelta(texto_normal):
    coincidencia = PATRON_HORA_SUELTA.match(texto_normal)
    if coincidencia:
        return _a_24_horas(int(coincidencia.group(1)), int(coincidencia.group(2) or 0), texto_normal)
    cantidad, _ = extraer_cantidad(texto_normal.split())
    return _a_24_horas(cantidad, 0, texto_normal) if cantidad else None


def extraer_personas(texto_normal):
    coincidencia = PATRON_PERSONAS.search(texto_normal)
    if not coincidencia:
        return None
    return _a_numero(next(g for g in coincidencia.groups() if g))


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-z0-9#\s]", " ", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()


def singular(palabra):
    if len(palabra) > 4 and palabra.endswith("es") and palabra[-3] not in "aeiou":
        return palabra[:-2]
    if len(palabra) > 3 and palabra.endswith("s"):
        return palabra[:-1]
    return palabra


def forma_canonica(texto):
    return " ".join(singular(p) for p in normalizar(texto).split())


def enmascarar_tarjetas(texto):
    return TARJETA.sub("[dato protegido]", texto or "")


def contiene(texto_normal, *frases):
    relleno = f" {texto_normal} "
    return any(f" {frase} " in relleno for frase in frases)


def extraer_cantidad(palabras):
    for indice, palabra in enumerate(palabras):
        if palabra.isdigit() and 0 < int(palabra) <= 999:
            return int(palabra), indice
        if palabra in NUMEROS and palabra not in ("un", "una"):
            return NUMEROS[palabra], indice
    for indice, palabra in enumerate(palabras):
        if palabra in ("un", "una", "uno"):
            return 1, indice
    return None, None


def extraer_numero_pedido(texto_normal):
    coincidencia = re.search(r"(?:pedido|orden|numero|#)\s*(?:numero\s*)?#?\s*(\d{1,9})", texto_normal)
    return int(coincidencia.group(1)) if coincidencia else None


def extraer_telefono(texto_normal):
    digitos = re.sub(r"\D", "", texto_normal)
    return digitos if 7 <= len(digitos) <= 13 else None


def formatear_pesos(valor):
    return f"{int(round(valor)):,}".replace(",", ".") + " pesos"
