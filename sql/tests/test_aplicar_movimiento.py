import threading

import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo
from test_movimiento_inventario import _crear_movimiento


def _crear_insumo_y_categoria(cursor, categoria_nombre="Lácteos", **overrides):
    categoria_id = _crear_categoria(cursor, nombre=categoria_nombre)
    return _crear_insumo(cursor, categoria_id, **overrides)


def _stock_actual(cursor, insumo_id):
    cursor.execute("SELECT stock_actual FROM item_inventario WHERE id = %s", (insumo_id,))
    return cursor.fetchone()[0]


def test_entrada_incrementa_stock_real(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    mov_id = _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=5)

    assert _stock_actual(cursor, insumo_id) == 5
    cursor.execute(
        "SELECT stock_anterior, stock_nuevo FROM movimiento_inventario WHERE id = %s",
        (mov_id,),
    )
    assert cursor.fetchone() == (0, 5)


def test_entrada_sin_compra_cubre_el_stock_inicial(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    mov_id = _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=8)
    cursor.execute("SELECT compra_id FROM movimiento_inventario WHERE id = %s", (mov_id,))
    assert cursor.fetchone() == (None,)
    assert _stock_actual(cursor, insumo_id) == 8


def test_entrada_con_compra_id_se_guarda(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    mov_id = _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=8,
                                compra_id=123)
    cursor.execute("SELECT compra_id FROM movimiento_inventario WHERE id = %s", (mov_id,))
    assert cursor.fetchone() == (123,)


def test_salida_descuenta_stock_real(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=10)
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=3)
    assert _stock_actual(cursor, insumo_id) == 7


def test_salida_rechaza_si_excede_stock_disponible(cursor):
    insumo_id = _crear_insumo_y_categoria(cursor)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=5)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=10)


def test_dos_salidas_concurrentes_no_dejan_stock_negativo(esquema, database_url):
    setup_conn = psycopg2.connect(database_url)
    setup_conn.autocommit = True
    with setup_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO categoria_insumo (nombre) VALUES ('ConcurrenciaT7') RETURNING id"
        )
        categoria_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO item_inventario (nombre, unidad_medida, categoria_id, sucursal_id)
            VALUES ('Insumo concurrencia T7', 'unidad', %s, 999)
            RETURNING id
            """,
            (categoria_id,),
        )
        insumo_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO movimiento_inventario
                (item_inventario_id, tipo, cantidad_movimiento, stock_anterior, usuario_id)
            VALUES (%s, 'ENTRADA', 5, 0, 1)
            """,
            (insumo_id,),
        )
    setup_conn.close()

    resultados = {}

    def intentar_salida(nombre):
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO movimiento_inventario
                        (item_inventario_id, tipo, cantidad_movimiento, stock_anterior, usuario_id)
                    VALUES (%s, 'SALIDA', 3, 0, 1)
                    """,
                    (insumo_id,),
                )
            conn.commit()
            resultados[nombre] = "OK"
        except psycopg2.Error:
            conn.rollback()
            resultados[nombre] = "RECHAZADO"
        finally:
            conn.close()

    hilo1 = threading.Thread(target=intentar_salida, args=("hilo1",))
    hilo2 = threading.Thread(target=intentar_salida, args=("hilo2",))
    hilo1.start()
    hilo2.start()
    hilo1.join()
    hilo2.join()

    verify_conn = psycopg2.connect(database_url)
    with verify_conn.cursor() as cur:
        cur.execute("SELECT stock_actual FROM item_inventario WHERE id = %s", (insumo_id,))
        stock_final = cur.fetchone()[0]
    verify_conn.close()

    assert stock_final >= 0
    # Con stock=5 y dos salidas de 3 cada una, solo una puede tener éxito.
    assert list(resultados.values()).count("OK") == 1
    assert list(resultados.values()).count("RECHAZADO") == 1
