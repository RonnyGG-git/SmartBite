import threading

import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo
from test_movimiento_inventario import _crear_movimiento


def _crear_insumo_con_minimo(cursor, stock_minimo, categoria_nombre="Lácteos", **overrides):
    categoria_id = _crear_categoria(cursor, nombre=categoria_nombre)
    return _crear_insumo(cursor, categoria_id, stock_minimo=stock_minimo, **overrides)


def _solicitudes_pendientes(cursor, insumo_id):
    cursor.execute(
        "SELECT cantidad_sugerida FROM solicitud_reabastecimiento "
        "WHERE item_inventario_id = %s AND estado = 'PENDIENTE'",
        (insumo_id,),
    )
    return cursor.fetchall()


def test_salida_bajo_minimo_genera_solicitud(cursor):
    insumo_id = _crear_insumo_con_minimo(cursor, stock_minimo=5)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=10)
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=8)  # stock queda en 2

    pendientes = _solicitudes_pendientes(cursor, insumo_id)
    assert pendientes == [(3,)]  # 5 (mínimo) - 2 (stock nuevo)


def test_no_genera_segunda_solicitud_mientras_la_primera_sigue_pendiente(cursor):
    insumo_id = _crear_insumo_con_minimo(cursor, stock_minimo=5)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=10)
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=8)  # stock=2, genera 1ra
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=1)  # stock=1, sigue bajo

    pendientes = _solicitudes_pendientes(cursor, insumo_id)
    assert len(pendientes) == 1


def test_sin_minimo_configurado_no_genera_solicitud(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(categoria_id=categoria_id, cursor=cursor)  # stock_minimo NULL
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=1)
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=1)  # stock=0

    assert _solicitudes_pendientes(cursor, insumo_id) == []


def test_ajuste_inmediato_bajo_minimo_genera_solicitud(cursor):
    insumo_id = _crear_insumo_con_minimo(cursor, stock_minimo=10)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=20)
    # Ajuste chico (diferencia 5, bajo el umbral default de 20): se aplica de inmediato.
    _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=15,
                       motivo="Conteo")  # todavía no baja del mínimo (15 > 10)
    assert _solicitudes_pendientes(cursor, insumo_id) == []

    _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=8,
                       motivo="Conteo, baja del mínimo")  # diferencia 7, bajo umbral, inmediato
    assert _solicitudes_pendientes(cursor, insumo_id) == [(2,)]  # 10 - 8


def test_ajuste_aprobado_bajo_minimo_genera_solicitud_recien_al_aprobar(cursor):
    insumo_id = _crear_insumo_con_minimo(cursor, stock_minimo=10)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=50)
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=5,
                                motivo="Ajuste grande, requiere aprobación")

    # Todavía pendiente de aprobación: no debe haber solicitud de reabastecimiento.
    assert _solicitudes_pendientes(cursor, insumo_id) == []

    cursor.execute(
        "UPDATE movimiento_inventario SET aprobado_por = %s WHERE id = %s", (99, mov_id)
    )
    assert _solicitudes_pendientes(cursor, insumo_id) == [(5,)]  # 10 - 5


def test_dos_salidas_concurrentes_generan_una_sola_solicitud(esquema, database_url):
    setup_conn = psycopg2.connect(database_url)
    setup_conn.autocommit = True
    with setup_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO categoria_insumo (nombre) VALUES ('ConcurrenciaT10') RETURNING id"
        )
        categoria_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO item_inventario (nombre, unidad_medida, categoria_id, sucursal_id, stock_minimo)
            VALUES ('Insumo concurrencia T10', 'unidad', %s, 998, 15)
            RETURNING id
            """,
            (categoria_id,),
        )
        insumo_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO movimiento_inventario
                (item_inventario_id, tipo, cantidad_movimiento, stock_anterior, usuario_id)
            VALUES (%s, 'ENTRADA', 20, 0, 1)
            """,
            (insumo_id,),
        )
    setup_conn.close()

    # Stock queda en 20 (min=15). Dos SALIDAs de 10 c/u: la primera deja el
    # stock en 10 (< 15, genera la solicitud); la segunda lo deja en 0
    # (< 15 también, pero ya hay una PENDIENTE — debe omitirse, no duplicar).
    def intentar_salida():
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO movimiento_inventario
                        (item_inventario_id, tipo, cantidad_movimiento, stock_anterior, usuario_id)
                    VALUES (%s, 'SALIDA', 10, 0, 1)
                    """,
                    (insumo_id,),
                )
            conn.commit()
        except psycopg2.Error:
            conn.rollback()
        finally:
            conn.close()

    hilo1 = threading.Thread(target=intentar_salida)
    hilo2 = threading.Thread(target=intentar_salida)
    hilo1.start()
    hilo2.start()
    hilo1.join()
    hilo2.join()

    verify_conn = psycopg2.connect(database_url)
    with verify_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM solicitud_reabastecimiento "
            "WHERE item_inventario_id = %s AND estado = 'PENDIENTE'",
            (insumo_id,),
        )
        cantidad_solicitudes = cur.fetchone()[0]
    verify_conn.close()

    assert cantidad_solicitudes == 1
