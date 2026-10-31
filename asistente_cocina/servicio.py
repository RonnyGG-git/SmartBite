from __future__ import annotations

from django.db.models import Max

from inventario.models import ItemInventario

from .models import RecetaSugerida
from .motor.buscador import Buscador, Sugerencia
from .motor.normalizar import normalizar

_cache: dict = {"firma": None, "buscador": None}


def _firmar_recetas() -> tuple:
    recetas = RecetaSugerida.objects.filter(activo=True)
    return (recetas.count(), recetas.aggregate(ultimo=Max("actualizado_en"))["ultimo"])


def obtener_buscador() -> Buscador | None:
    firma = _firmar_recetas()
    if _cache["firma"] == firma and _cache["buscador"] is not None:
        return _cache["buscador"]

    recetas = RecetaSugerida.objects.filter(activo=True)
    filas = list(recetas.only("nombre", "descripcion", "categoria", "dificultad",
                              "tiempo_min", "porciones", "ingredientes", "etiquetas"))
    datos = [_receta_a_dictico(fila) for fila in filas]

    buscador = Buscador(datos) if datos else None
    _cache["firma"] = firma
    _cache["buscador"] = buscador
    return buscador


def _receta_a_dictico(receta: RecetaSugerida) -> dict:
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
    if not sucursal_id or not sugerencias:
        return

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
    buscador = obtener_buscador()
    if buscador is None:
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
