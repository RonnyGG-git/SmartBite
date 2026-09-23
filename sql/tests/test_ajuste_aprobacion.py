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


# --- Verificación posterior (2026-09-23) ---

def test_umbral_de_una_transaccion_anterior_no_rompe_el_siguiente_ajuste(conn):
    # Mismo problema que app.usuario_actual: tras un SET LOCAL la variable
    # queda en '' y ''::NUMERIC tumbaba todo AJUSTE posterior en la conexión.
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.umbral_ajuste_aprobacion = 5")
    conn.rollback()
    with conn.cursor() as cur:
        insumo_id = _crear_insumo_con_stock(cur, 50)
        _crear_movimiento(cur, insumo_id, "AJUSTE", cantidad_objetivo=55, motivo="Conteo físico")
        assert _stock_actual(cur, insumo_id) == 55  # vuelve al default (20)


def test_rechaza_aprobar_un_ajuste_que_no_estaba_pendiente(cursor):
    # Antes, "aprobar" un ajuste que ya se había aplicado solo volvía a fijar
    # el stock y borraba en silencio el efecto de los movimientos posteriores.
    insumo_id = _crear_insumo_con_stock(cursor, 10)
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=8,
                                motivo="Conteo físico")
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=5)  # stock 13
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            "UPDATE movimiento_inventario SET aprobado_por = 99 WHERE id = %s", (mov_id,)
        )


def test_rechaza_aprobar_dos_veces(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 50)
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=100,
                                motivo="Conteo físico con diferencia grande")
    cursor.execute("UPDATE movimiento_inventario SET aprobado_por = 99 WHERE id = %s", (mov_id,))
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            "UPDATE movimiento_inventario SET aprobado_por = 98 WHERE id = %s", (mov_id,)
        )


def test_aprobar_ajuste_registra_el_stock_real_al_momento_de_aprobar(cursor):
    # El kardex tiene que encadenar: si entre la solicitud y la aprobación
    # entró mercancía, el stock_anterior del ajuste es el de ese momento.
    insumo_id = _crear_insumo_con_stock(cursor, 100)
    mov_id = _crear_movimiento(cursor, insumo_id, "AJUSTE", cantidad_objetivo=10,
                                motivo="Conteo físico con diferencia grande")
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=50)  # stock real 150
    cursor.execute("UPDATE movimiento_inventario SET aprobado_por = 99 WHERE id = %s", (mov_id,))
    cursor.execute(
        "SELECT stock_anterior, stock_nuevo FROM movimiento_inventario WHERE id = %s", (mov_id,)
    )
    assert cursor.fetchone() == (150, 10)
    assert _stock_actual(cursor, insumo_id) == 10
