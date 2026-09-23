import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual
from test_movimiento_inventario import _crear_movimiento


def _crear_insumo_con_stock(cursor, stock_inicial):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=stock_inicial)
    return insumo_id


def _stock_actual(cursor, insumo_id):
    cursor.execute("SELECT stock_actual FROM item_inventario WHERE id = %s", (insumo_id,))
    return cursor.fetchone()[0]


def test_ajuste_bajo_el_umbral_se_aplica_de_inmediato(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 50)
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=55,
                                motivo="Conteo físico")

    assert _stock_actual(cursor, insumo_id) == 55
    cursor.execute(
        "SELECT requiere_aprobacion, stock_nuevo FROM movimiento_inventario WHERE id = %s",
        (mov_id,),
    )
    assert cursor.fetchone() == (False, 55)


def test_ajuste_sobre_el_umbral_queda_pendiente_sin_tocar_el_stock(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 50)
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=100,
                                motivo="Conteo físico con diferencia grande")

    # El stock del insumo NO cambia todavía.
    assert _stock_actual(cursor, insumo_id) == 50
    cursor.execute(
        "SELECT requiere_aprobacion, stock_nuevo, aprobado_por FROM movimiento_inventario WHERE id = %s",
        (mov_id,),
    )
    assert cursor.fetchone() == (True, None, None)


def test_aprobar_ajuste_pendiente_recien_ahi_aplica_el_stock(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 50)
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=100,
                                motivo="Conteo físico con diferencia grande")
    assert _stock_actual(cursor, insumo_id) == 50  # todavía pendiente

    _set_usuario_actual(cursor, 1)  # no aplica a este trigger, pero no debe romper nada
    cursor.execute(
        "UPDATE movimiento_inventario SET aprobado_por = %s WHERE id = %s",
        (99, mov_id),
    )

    assert _stock_actual(cursor, insumo_id) == 100
    cursor.execute(
        "SELECT stock_nuevo, aprobado_en IS NOT NULL FROM movimiento_inventario WHERE id = %s",
        (mov_id,),
    )
    assert cursor.fetchone() == (100, True)


def test_umbral_configurable_por_sesion(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 50)
    cursor.execute("SET LOCAL app.umbral_ajuste_aprobacion = 5")

    # Con el default (20) esta diferencia de 10 se aplicaría directo; con
    # el umbral bajado a 5, debe quedar pendiente de aprobación.
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=60,
                                motivo="Ajuste chico, umbral bajado")

    assert _stock_actual(cursor, insumo_id) == 50
    cursor.execute(
        "SELECT requiere_aprobacion FROM movimiento_inventario WHERE id = %s", (mov_id,)
    )
    assert cursor.fetchone() == (True,)
