import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual
from test_movimiento_inventario import _crear_movimiento


def _crear_insumo_con_stock(cursor, stock_inicial, categoria_nombre="Lácteos", **overrides):
    categoria_id = _crear_categoria(cursor, nombre=categoria_nombre)
    insumo_id = _crear_insumo(cursor, categoria_id, **overrides)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=stock_inicial)
    return insumo_id


def _stock_actual(cursor, insumo_id):
    cursor.execute("SELECT stock_actual FROM item_inventario WHERE id = %s", (insumo_id,))
    return cursor.fetchone()[0]


def test_perdida_manual_descuenta_stock(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 10)
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=4,
                       causa_perdida="DANIO", origen_perdida="MANUAL",
                       motivo="Se cayó una caja")
    assert _stock_actual(cursor, insumo_id) == 6


def test_perdida_manual_rechaza_si_excede_stock(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 5)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=10,
                           causa_perdida="EXTRAVIO", origen_perdida="MANUAL",
                           motivo="No aparece")


def test_generar_perdidas_vencimiento_insumo_vencido_sin_usar(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 8, fecha_vencimiento="2020-01-01")

    cursor.execute("SELECT fn_generar_perdidas_vencimiento()")
    generadas = cursor.fetchone()[0]

    assert generadas == 1
    assert _stock_actual(cursor, insumo_id) == 0
    cursor.execute(
        """
        SELECT tipo, cantidad_movimiento, causa_perdida, origen_perdida
        FROM movimiento_inventario
        WHERE item_inventario_id = %s AND causa_perdida = 'VENCIMIENTO'
        """,
        (insumo_id,),
    )
    assert cursor.fetchone() == ("SALIDA", 8, "VENCIMIENTO", "AUTOMATICA")


def test_generar_perdidas_vencimiento_no_afecta_insumo_no_vencido(cursor):
    _crear_insumo_con_stock(cursor, 8, fecha_vencimiento="2099-01-01")
    cursor.execute("SELECT fn_generar_perdidas_vencimiento()")
    assert cursor.fetchone()[0] == 0


def test_generar_perdidas_vencimiento_no_afecta_insumo_sin_fecha(cursor):
    _crear_insumo_con_stock(cursor, 8)  # sin fecha_vencimiento
    cursor.execute("SELECT fn_generar_perdidas_vencimiento()")
    assert cursor.fetchone()[0] == 0


def test_rechaza_segunda_perdida_manual_por_vencimiento_el_mismo_dia(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 8, fecha_vencimiento="2020-01-01")
    cursor.execute("SELECT fn_generar_perdidas_vencimiento()")
    assert cursor.fetchone()[0] == 1  # ya generó la pérdida automática

    with pytest.raises(psycopg2.errors.RaiseException):
        _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=1,
                           causa_perdida="VENCIMIENTO", origen_perdida="MANUAL",
                           motivo="Reporte manual duplicado")


def test_permite_perdida_manual_por_otra_causa_el_mismo_dia(cursor):
    insumo_id = _crear_insumo_con_stock(cursor, 8, fecha_vencimiento="2020-01-01")
    cursor.execute("SELECT fn_generar_perdidas_vencimiento()")
    assert cursor.fetchone()[0] == 1

    # Mismo insumo: entra mercancía nueva y se daña una parte. RF-38 solo
    # mira la causa VENCIMIENTO, así que una pérdida por DANIO no se bloquea.
    # (Verificación posterior: antes este test usaba OTRO insumo, y así no
    # probaba nada de RF-38 — el chequeo es por insumo.)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=5)
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=2,
                       causa_perdida="DANIO", origen_perdida="MANUAL",
                       motivo="Golpe en bodega")
    assert _stock_actual(cursor, insumo_id) == 3


# --- Verificación posterior (2026-09-23) ---

def test_perdidas_automaticas_no_se_omiten_si_la_sesion_ya_uso_set_local(conn):
    # Con app.usuario_actual en '' (tras un SET LOCAL previo en la misma
    # conexión), cada INSERT de pérdida fallaba por el cast y el EXCEPTION
    # WHEN OTHERS de la función lo tragaba: devolvía 0 sin avisar.
    with conn.cursor() as cur:
        _set_usuario_actual(cur, 1)
    conn.rollback()
    with conn.cursor() as cur:
        insumo_id = _crear_insumo_con_stock(cur, 4, fecha_vencimiento="2020-01-01")
        cur.execute("SELECT fn_generar_perdidas_vencimiento()")
        assert cur.fetchone()[0] == 1
        assert _stock_actual(cur, insumo_id) == 0


def test_registrar_perdida_de_un_insumo_inactivo(cursor):
    # Dar de baja un insumo no debe impedir sacar el stock que le quedó. El
    # trigger de RF-7 lo bloqueaba con un mensaje engañoso ("ya está
    # inactivo") porque se disparaba en cualquier UPDATE del insumo.
    insumo_id = _crear_insumo_con_stock(cursor, 6)
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))
    _crear_movimiento(cursor, insumo_id, "SALIDA", cantidad_movimiento=6,
                       causa_perdida="DANIO", origen_perdida="MANUAL",
                       motivo="Retiro del stock restante")
    assert _stock_actual(cursor, insumo_id) == 0
