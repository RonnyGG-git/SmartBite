"""Base de conocimiento y bitácora del Asistente de Recomendación de Recetas.

El asistente NO evalúa órdenes: responde consultas de recetas en lenguaje
natural ("algo dulce y fácil de hacer"). Esta app guarda las recetas que
alimentan el índice TF-IDF y la bitácora de búsquedas, que luego sirve
para medir si las recomendaciones sirvieron.
"""

from django.db import models

from core.models import TimestampedModel


class RecetaSugerida(TimestampedModel):
    """Una receta de la base de conocimiento del asistente.

    `ingredientes` y `pasos` son JSONField porque su forma cambia por
    receta y no se consulta por SQL: solo se leen al indexar para construir
    `texto_busqueda` y se guardan tal cual para mostrarlos en la respuesta.
    """

    ENTRADA = "ENTRADA"
    PLATO_FUERTE = "PLATO_FUERTE"
    POSTRE = "POSTRE"
    BEBIDA = "BEBIDA"
    ACOMPANANTE = "ACOMPANANTE"
    CATEGORIA_CHOICES = [
        (ENTRADA, "Entrada"),
        (PLATO_FUERTE, "Plato fuerte"),
        (POSTRE, "Postre"),
        (BEBIDA, "Bebida"),
        (ACOMPANANTE, "Acompañante"),
    ]

    FACIL = "FACIL"
    MEDIA = "MEDIA"
    DIFICIL = "DIFICIL"
    DIFICULTAD_CHOICES = [
        (FACIL, "Fácil"),
        (MEDIA, "Media"),
        (DIFICIL, "Difícil"),
    ]

    nombre = models.CharField(max_length=150, unique=True)
    descripcion = models.CharField(max_length=255)
    categoria = models.CharField(max_length=20, choices=CATEGORIA_CHOICES)
    dificultad = models.CharField(max_length=10, choices=DIFICULTAD_CHOICES)
    tiempo_min = models.PositiveIntegerField()
    porciones = models.PositiveIntegerField(default=4)
    # Lista de strings (nombres de ingredientes) y de strings (instrucciones).
    ingredientes = models.JSONField(default=list)
    pasos = models.JSONField(default=list)
    etiquetas = models.CharField(max_length=255, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    # Mismo valor que CATEGORIA_CHOICES: TfidfVectorizer no puede usar
    # etiquetas con acentos ni espacios, solo el código.
    CATEGORIA_TERMINOS = {
        ENTRADA: "entrada",
        PLATO_FUERTE: "plato principal",
        POSTRE: "postre",
        BEBIDA: "bebida",
        ACOMPANANTE: "acompanamiento",
    }

    def texto_busqueda(self) -> str:
        """Texto plano que se indexa con TF-IDF, ya normalizado.

        Concatena todo lo que un usuario podría escribir para encontrar esta
        receta: nombre, descripción, ingredientes, etiquetas y la categoría
        en palabras legibles ("POSTRE" -> "postre"), para que una consulta
        como "algo dulce" tenga con qué coincidir.

        Se normaliza aquí y no al indexar a propósito: la consulta del
        usuario también llega normalizada, y si el documento conservara
        mayúsculas o tildes ("Arroz con Pollo", "ñapa") no cruzaría ni una
        sola palabra con ella, porque el vectorizador distingue "Arroz" de
        "arroz".
        """
        from .motor.normalizar import normalizar

        partes = [self.nombre, self.descripcion, self.etiquetas]
        partes.append(self.CATEGORIA_TERMINOS.get(self.categoria, self.categoria.lower()))
        # ingredientes llega como lista de nombres, pero la base de conocimiento
        # podría guardar objetos {"nombre": ...}; se cubren las dos formas para
        # que un dato raro no rompa el indexado de toda la receta.
        for ingrediente in self.ingredientes or []:
            if isinstance(ingrediente, dict):
                partes.append(str(ingrediente.get("nombre", "")))
            else:
                partes.append(str(ingrediente))
        return normalizar(" ".join(parte for parte in partes if parte))


class ConsultaAsistente(TimestampedModel):
    """Bitácora de una búsqueda hecha al asistente.

    Se guarda cada consulta con lo que el motor entendió (`filtros_detectados`),
    lo que devolvió (`resultados`) y si le sirvió al usuario (`util`, que se
    rellena después). Es lo que permite medir calidad más adelante: sin
    bitácora no hay forma de saber si las recomendaciones acertan.
    """

    usuario = models.ForeignKey(
        "cuentas.Usuario",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consultas_asistente",
    )
    texto = models.CharField(max_length=300)
    filtros_detectados = models.JSONField(default=dict)
    resultados = models.JSONField(default=list)
    # null=True (y no False) para distinguir "aún no sabemos si le sirvió"
    # de "el usuario dijo que no le sirvió".
    util = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return self.texto[:60]
