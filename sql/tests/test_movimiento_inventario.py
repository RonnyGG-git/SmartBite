import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo


def _crear_movimiento(cursor, item_inventario_id, tipo, usuario_id=1, **overrides):
    columnas = dict(
        item_inventario_id=item_inventario_id,
        tipo=tipo,
        stock_anterior=overrides.pop("stock_anterior", 10),
        usuario_id=usuario_id,
        **overrides,
    )
    campos = ", ".join(columnas.keys())
    placeholders = ", ".join(["%s"] * len(columnas))
    cursor.execute(
        f"INSERT INTO movimiento_inventario ({campos}) VALUES ({placeholders}) RETURNING id",
        list(columnas.values()),
    )
    return cursor.fetchone()[0]


def _crear_insumo_y_categoria(cursor, categoria_nombre="Lácteos", **overrides):
    categoria_id = _crear_categoria(cursor, nombre=categoria_nombre)
    return _crear_insumo(cursor, categoria_id, **overrides)


def test_kardex_registra_fecha_usuario_insumo_tipo_y_cantidad(cursor):
    # RF-18: cada movimiento queda trazable con estos 5 datos juntos — no
    # alcanza con que la fila se inserte, hay que leerlos de vuelta.
    insumo_id = _crear_insumo_y_categoria(cursor)
    mov_id = _crear_movimiento(cursor, insumo_id, "ENTRADA", usuario_id=7,
                                cantidad_movimiento=4)

    cursor.execute(
        """
        SELECT item_inventario_id, tipo, cantidad_movimiento, usuario_id,
               creado_en IS NOT NULL
        FROM movimiento_inventario WHERE id = %s
        """,
        (mov_id,),
    )
    assert cursor.fetchone() == (insumo_id, "ENTRADA", 4, 7, True)


def test_insertar_entrada_valida(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    mov_id = _crear_movimiento(
        cursor, insumo_id, "ENTRADA",
        cantidad_movimiento=5, stock_anterior=10, stock_nuevo=15,
    )
    assert mov_id is not None


def test_insertar_salida_valida(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    # Stock real primero (T7 calcula stock_anterior/stock_nuevo de verdad,
    # ya no se puede simular con valores sueltos como en T6).
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=10)
    mov_id = _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=3)
    assert mov_id is not None


def test_insertar_ajuste_valido_con_motivo(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    mov_id = _crear_movimiento(
        cursor, insumo_id, "AJUSTE",
        cantidad_objetivo=8, stock_anterior=10, stock_nuevo=8,
        motivo="Conteo físico",
    )
    assert mov_id is not None


def test_rechaza_ajuste_sin_motivo(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_movimiento(
            cursor, insumo_id, "AJUSTE",
            cantidad_objetivo=8, stock_anterior=10, stock_nuevo=8,
        )


def test_rechaza_entrada_sin_cantidad_movimiento(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_movimiento(cursor, insumo_id, "ENTRADA", stock_anterior=10)


def test_rechaza_ajuste_con_cantidad_movimiento(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_movimiento(
            cursor, insumo_id, "AJUSTE",
            cantidad_movimiento=5, cantidad_objetivo=8,
            stock_anterior=10, motivo="Conteo físico",
        )


def test_consultar_movimientos_filtrando_por_insumo_tipo_y_fecha(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    otro_insumo_id = _crear_insumo_y_categoria(cursor, categoria_nombre="Cárnicos",
                                                nombre="Otro insumo")

    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=5)
    reciente_id = _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=2)
    _crear_movimiento(cursor, otro_insumo_id, "ENTRADA", cantidad_movimiento=5)
    _crear_movimiento(cursor, otro_insumo_id, "SALIDA", cantidad_movimiento=1)

    # Retrocedemos la fecha del primer movimiento para poder filtrar por rango.
    cursor.execute(
        "UPDATE movimiento_inventario SET creado_en = now() - interval '10 days' "
        "WHERE item_inventario_id = %s AND tipo = 'ENTRADA'",
        (insumo_id,),
    )

    cursor.execute(
        """
        SELECT id FROM movimiento_inventario
        WHERE item_inventario_id = %s AND tipo = 'SALIDA'
          AND creado_en >= now() - interval '1 day'
        """,
        (insumo_id,),
    )
    assert [r[0] for r in cursor.fetchall()] == [reciente_id]
