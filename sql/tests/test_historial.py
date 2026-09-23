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


def test_sin_usuario_actual_falla_con_error_claro_aunque_la_sesion_ya_lo_haya_usado(conn):
    # Tras un SET LOCAL, Postgres deja la variable definida con valor ''
    # (no NULL) el resto de la sesión. El cast ''::BIGINT fallaba con
    # "invalid input syntax" en vez del NotNullViolation documentado.
    with conn.cursor() as cur:
        _set_usuario_actual(cur, 1)
    conn.rollback()
    with conn.cursor() as cur:
        categoria_id = _crear_categoria(cur)
        insumo_id = _crear_insumo(cur, categoria_id)
        with pytest.raises(psycopg2.errors.NotNullViolation):
            cur.execute(
                "UPDATE item_inventario SET nombre = 'Otro' WHERE id = %s", (insumo_id,)
            )


def test_cambio_de_unidad_y_sucursal_quedan_en_historial(cursor):
    # RF-4 dice "cada campo modificado": unidad_medida y sucursal_id
    # faltaban en el trigger.
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id, unidad_medida="kg")
    _set_usuario_actual(cursor, 42)
    cursor.execute(
        "UPDATE item_inventario SET unidad_medida = 'g', sucursal_id = 2 WHERE id = %s",
        (insumo_id,),
    )
    cursor.execute(
        """
        SELECT campo, valor_anterior, valor_nuevo FROM item_inventario_historial
        WHERE item_inventario_id = %s ORDER BY campo
        """,
        (insumo_id,),
    )
    assert cursor.fetchall() == [("sucursal_id", "1", "2"), ("unidad_medida", "kg", "g")]


@pytest.mark.parametrize("sentencia", [
    "UPDATE item_inventario_historial SET valor_nuevo = 'alterado' WHERE item_inventario_id = %s",
    "DELETE FROM item_inventario_historial WHERE item_inventario_id = %s",
])
def test_historial_no_se_edita_ni_se_borra(cursor, sentencia):
    # Verificación posterior (2026-09-23): un changelog editable no audita nada.
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id, nombre="Leche entera")
    _set_usuario_actual(cursor, 42)
    cursor.execute("UPDATE item_inventario SET nombre = 'Leche' WHERE id = %s", (insumo_id,))
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (insumo_id,))
