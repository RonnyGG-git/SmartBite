import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual


def test_reporte_filtra_por_categoria(cursor):
    categoria_a = _crear_categoria(cursor, nombre="Lácteos")
    categoria_b = _crear_categoria(cursor, nombre="Cárnicos")
    _crear_insumo(cursor, categoria_a, nombre="Leche")
    _crear_insumo(cursor, categoria_b, nombre="Carne")

    cursor.execute(
        "SELECT nombre FROM vista_reporte_inventario WHERE categoria = %s", ("Lácteos",)
    )
    assert [r[0] for r in cursor.fetchall()] == ["Leche"]


def test_reporte_filtra_por_estado(cursor):
    categoria_id = _crear_categoria(cursor)
    activo_id = _crear_insumo(cursor, categoria_id, nombre="Activo")
    inactivo_id = _crear_insumo(cursor, categoria_id, nombre="Inactivo")
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (inactivo_id,))

    cursor.execute(
        "SELECT id FROM vista_reporte_inventario WHERE activo = true AND id IN (%s, %s)",
        (activo_id, inactivo_id),
    )
    assert [r[0] for r in cursor.fetchall()] == [activo_id]


def test_reporte_filtra_por_rango_de_fechas(cursor):
    categoria_id = _crear_categoria(cursor)
    viejo_id = _crear_insumo(cursor, categoria_id, nombre="Viejo")
    reciente_id = _crear_insumo(cursor, categoria_id, nombre="Reciente")
    cursor.execute(
        "UPDATE item_inventario SET creado_en = now() - interval '30 days' WHERE id = %s",
        (viejo_id,),
    )

    cursor.execute(
        "SELECT id FROM vista_reporte_inventario "
        "WHERE creado_en >= now() - interval '1 day' AND id IN (%s, %s)",
        (viejo_id, reciente_id),
    )
    assert [r[0] for r in cursor.fetchall()] == [reciente_id]


def test_reporte_sin_coincidencias_devuelve_vacio(cursor):
    categoria_id = _crear_categoria(cursor)
    _crear_insumo(cursor, categoria_id, nombre="Cualquiera")

    cursor.execute(
        "SELECT * FROM vista_reporte_inventario WHERE categoria = %s",
        ("Categoría que no existe",),
    )
    assert cursor.fetchall() == []
