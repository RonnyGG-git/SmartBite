import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual


def test_genera_codigo_con_prefijo_de_categoria(cursor):
    categoria_id = _crear_categoria(cursor, nombre="Lácteos")
    insumo_id = _crear_insumo(cursor, categoria_id, sucursal_id=1)
    cursor.execute("SELECT codigo_unico FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone()[0] == "LAC-00001"


def test_codigos_consecutivos_misma_categoria_y_sucursal(cursor):
    categoria_id = _crear_categoria(cursor, nombre="Lácteos")
    id1 = _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche")
    id2 = _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Yogur")
    cursor.execute(
        "SELECT id, codigo_unico FROM item_inventario WHERE id IN (%s, %s) ORDER BY id",
        (id1, id2),
    )
    codigos = [c for _, c in cursor.fetchall()]
    assert codigos == ["LAC-00001", "LAC-00002"]


def test_dos_sucursales_no_chocan_con_el_mismo_prefijo(cursor):
    # Antes de la corrección del plan, el UNIQUE era global y esto fallaba.
    categoria_id = _crear_categoria(cursor, nombre="Lácteos")
    id_sucursal_1 = _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche")
    id_sucursal_2 = _crear_insumo(cursor, categoria_id, sucursal_id=2, nombre="Leche")
    cursor.execute(
        "SELECT sucursal_id, codigo_unico FROM item_inventario WHERE id IN (%s, %s)",
        (id_sucursal_1, id_sucursal_2),
    )
    codigos = dict(cursor.fetchall())
    assert codigos == {1: "LAC-00001", 2: "LAC-00001"}


def test_rechaza_modificar_codigo_unico(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            "UPDATE item_inventario SET codigo_unico = 'OTRO-00001' WHERE id = %s",
            (insumo_id,),
        )


def test_permite_actualizar_otros_campos_sin_tocar_el_codigo(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    cursor.execute("SELECT codigo_unico FROM item_inventario WHERE id = %s", (insumo_id,))
    codigo_original = cursor.fetchone()[0]

    _set_usuario_actual(cursor, 1)
    cursor.execute(
        "UPDATE item_inventario SET descripcion = %s WHERE id = %s",
        ("Actualizado", insumo_id),
    )
    cursor.execute("SELECT codigo_unico FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone()[0] == codigo_original
