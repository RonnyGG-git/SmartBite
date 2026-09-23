import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual


def test_actualizar_dos_campos_crea_dos_filas_de_historial(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id, nombre="Leche entera",
                               costo_unitario=4000)
    _set_usuario_actual(cursor, 42)

    cursor.execute(
        "UPDATE item_inventario SET nombre = %s, costo_unitario = %s WHERE id = %s",
        ("Leche deslactosada", 4500, insumo_id),
    )

    cursor.execute(
        """
        SELECT campo, valor_anterior, valor_nuevo, usuario_id
        FROM item_inventario_historial
        WHERE item_inventario_id = %s
        ORDER BY campo
        """,
        (insumo_id,),
    )
    filas = cursor.fetchall()
    assert filas == [
        ("costo_unitario", "4000.00", "4500.00", 42),
        ("nombre", "Leche entera", "Leche deslactosada", 42),
    ]


def test_actualizar_a_el_mismo_valor_no_crea_historial(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id, nombre="Leche entera")
    _set_usuario_actual(cursor, 42)

    cursor.execute(
        "UPDATE item_inventario SET nombre = %s WHERE id = %s",
        ("Leche entera", insumo_id),
    )

    cursor.execute(
        "SELECT COUNT(*) FROM item_inventario_historial WHERE item_inventario_id = %s",
        (insumo_id,),
    )
    assert cursor.fetchone() == (0,)


def test_sin_usuario_actual_falla_con_error_claro(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id, nombre="Leche entera")
    # A propósito, no se llama a _set_usuario_actual.
    with pytest.raises(psycopg2.errors.NotNullViolation):
        cursor.execute(
            "UPDATE item_inventario SET nombre = %s WHERE id = %s",
            ("Leche deslactosada", insumo_id),
        )
