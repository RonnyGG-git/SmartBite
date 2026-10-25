import re
import unicodedata

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
