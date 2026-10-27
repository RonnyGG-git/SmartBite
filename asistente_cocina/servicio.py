"""Servicio integrador: conecta el motor matemático con la base de datos.

Hasta la Fase 2 el buscador funcionaba sobre diccionarios sueltos. Aquí se
conecta con `RecetaSugerida` e `ItemInventario` para que la respuesta al
chef diga no solo qué receta encaja, sino si además puede hacerla hoy con
lo que hay en la despensa de esa sucursal.

CACHÉ DEL BUSCADOR
------------------
La matriz TF-IDF no cambia entre peticiones y construirla cuesta más que
la propia búsqueda: refitarla en cada request saturaría el CPU (la skill
`performance` lo dice claro: cachear, no repetir trabajo). Se cachea en
memoria del proceso y se invalida comparando una "firma":

    (cantidad de recetas activas, última actualización)

Si alguien edita una receta, cambia `actualizado_en` y la firma cambia, así
que el índice se reconstruye. Si alguien borra una receta, cambia el
conteo. Es invalidación por contenido, no por tiempo: no hay ventana en la
que el usuario reciba recomendaciones de recetas que ya no existen.

Límite conocido: es caché por proceso. Con varias réplicas de gunicorn cada
una mantiene la suya, y cada una se entera de los cambios por su cuenta en
la siguiente petición (no hay que invalidar nada, solo se compara la firma).

Otro límite, medido: `QuerySet.update()` en bulk NO dispara `auto_now`, así
que una edición hecha por esa vía deja la firma igual y la caché sirve datos
viejos hasta que cambie otra cosa. El camino normal (`save()`, que es lo que
usan el admin y los formularios) sí invalida, igual que crear o desactivar
una receta.
"""

from __future__ import annotations

from django.db.models import Max

from inventario.models import ItemInventario

from .models import RecetaSugerida
from .motor.buscador import Buscador, Sugerencia
from .motor.normalizar import normalizar

# Caché del proceso. "firma" es la huella de la base de recetas; si no
# cambia, el buscador que ya está construido sigue sirviendo.
_cache: dict = {"firma": None, "buscador": None}


def _firmar_recetas() -> tuple:
    """Huella barata de la base de recetas: (conteo, última modificación).

    Son dos agregaciones en una sola consulta, no un SELECT de todas las
    filas: se paga en cada petición, así que tiene que ser barato.
    """
    recetas = RecetaSugerida.objects.filter(activo=True)
    return (recetas.count(), recetas.aggregate(ultimo=Max("actualizado_en"))["ultimo"])


def obtener_buscador() -> Buscador | None:
    """Devuelve el buscador, reconstruyéndolo solo si la base cambió."""
    firma = _firmar_recetas()
    if _cache["firma"] == firma and _cache["buscador"] is not None:
        return _cache["buscador"]

    recetas = RecetaSugerida.objects.filter(activo=True)
    # only() recorta las columnas trayendo UNA fila por receta en vez de
    # todas. La lista debe incluir exactamente los campos que luego lee
    # _receta_a_dictico: faltar uno convierte esto en un N+1 silencioso.
    filas = list(recetas.only("nombre", "descripcion", "categoria", "dificultad",
                              "tiempo_min", "porciones", "ingredientes", "etiquetas"))
    datos = [_receta_a_dictico(fila) for fila in filas]

    buscador = Buscador(datos) if datos else None
    _cache["firma"] = firma
    _cache["buscador"] = buscador
    return buscador


def _receta_a_dictico(receta: RecetaSugerida) -> dict:
    """Vuelca una receta al contrato de diccionarios que espera el motor.

    `ingredientes` es una lista de {"nombre": ..., "cantidad": ...}; el
    motor trabaja con nombres, así que aquí se aplana a una lista de
    strings normalizados. Se conserva el original por si hace falta.
    """
    ingredientes = [
        normalizar(ingrediente["nombre"])
        for ingrediente in (receta.ingredientes or [])
        if isinstance(ingrediente, dict) and ingrediente.get("nombre")
    ]
    return {
        "id": receta.pk,
        "nombre": receta.nombre,
        "descripcion": receta.descripcion,
        "categoria": receta.categoria,
        "dificultad": receta.dificultad,
        "tiempo_min": receta.tiempo_min,
        "porciones": receta.porciones,
        "ingredientes": ingredientes,
        "ingredientes_originales": receta.ingredientes or [],
        "etiquetas": receta.etiquetas,
        "texto_busqueda": receta.texto_busqueda(),
    }


def marcar_inventario(sugerencias: list[Sugerencia], sucursal_id: int = None) -> None:
    """Anota cada sugerencia con si sus ingredientes existen y hay stock.

    Modifica las sugerencias en el sitio (no devuelve una copia) porque son
    objetos volátiles creados por el buscador en esta misma petición.

    Sin sucursal no hay despensa contra la que comparar: un restaurante con
    varias sucursales no tiene "el stock", tiene "el stock de esta", así que
    sin ese dato la respuesta sería inventada. Se sale sin tocar nada.
    """
    if not sucursal_id or not sugerencias:
        return

    # Una sola consulta para toda la despensa, no una por ingrediente: con
    # cinco recetas de seis ingredientes serían treinta viajes a la BD.
    items = ItemInventario.objects.filter(
        sucursal_id=sucursal_id, activo=True
    ).only("nombre", "stock_actual")
    despensa = {
        normalizar(item.nombre): item.stock_actual
        for item in items
    }

    for sugerencia in sugerencias:
        estado = []
        for ingrediente in sugerencia.receta.get("ingredientes_originales") or []:
            nombre = ingrediente.get("nombre") if isinstance(ingrediente, dict) else ingrediente
            if not nombre:
                continue
            clave = normalizar(str(nombre))
            stock = despensa.get(clave)
            estado.append({
                "nombre": str(nombre),
                "existe": stock is not None,
                "con_stock": bool(stock and stock > 0),
                "stock_actual": stock,
            })
        sugerencia.inventario = estado


def consultar(texto: str, sucursal_id: int = None) -> dict:
    """Punto de entrada del asistente: consulta en lenguaje natural.

    Devuelve filtros, sugerencias y el estado de despensa de cada una.
    """
    buscador = obtener_buscador()
    if buscador is None:
        # Base de recetas vacía: no es un error, es un asistente sin
        # conocimiento todavía. Se responde controlado para que la vista no
        # tenga que inventar la forma de la respuesta.
        return {
            "filtros": {"categoria": None, "dificultad": None,
                        "tiempo_max": None, "ingredientes": []},
            "texto_procesado": normalizar(texto),
            "sugerencias": [],
            "cercanas": [],
            "consultable": False,
            "aviso": "Todavía no hay recetas cargadas en la base de conocimiento.",
        }

    resultado = buscador.buscar(texto)
    marcar_inventario(resultado["sugerencias"], sucursal_id)
    marcar_inventario(resultado["cercanas"], sucursal_id)
    resultado["consultable"] = True
    return resultado
