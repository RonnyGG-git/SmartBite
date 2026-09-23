import json

import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual
from test_movimiento_inventario import _crear_movimiento


def _crear_insumo_simple(cursor, categoria_nombre="Lácteos", **overrides):
    categoria_id = _crear_categoria(cursor, nombre=categoria_nombre)
    return _crear_insumo(cursor, categoria_id, **overrides)


# --- control de existencias (RF-10, RF-11, RF-33) ---

def test_control_existencias_incluye_insumo_bajo_minimo(cursor):
    insumo_id = _crear_insumo_simple(cursor, stock_minimo=10)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=3)

    cursor.execute(
        "SELECT id FROM vista_control_existencias WHERE id = %s", (insumo_id,)
    )
    assert cursor.fetchone() == (insumo_id,)


def test_control_existencias_respeta_sucursal(cursor):
    # RF-10: "todos los insumos DE UNA SUCURSAL" — no basta con que la
    # columna exista, hay que confirmar el filtro por sucursal_id.
    categoria_id = _crear_categoria(cursor)
    bajo_en_sucursal_1 = _crear_insumo(cursor, categoria_id, sucursal_id=1,
                                        nombre="Bajo en suc 1", stock_minimo=10)
    _crear_movimiento(cursor, bajo_en_sucursal_1, "ENTRADA", cantidad_movimiento=2)
    bajo_en_sucursal_2 = _crear_insumo(cursor, categoria_id, sucursal_id=2,
                                        nombre="Bajo en suc 2", stock_minimo=10)
    _crear_movimiento(cursor, bajo_en_sucursal_2, "ENTRADA", cantidad_movimiento=2)

    cursor.execute(
        "SELECT id FROM vista_control_existencias WHERE sucursal_id = 1 "
        "AND id IN (%s, %s)",
        (bajo_en_sucursal_1, bajo_en_sucursal_2),
    )
    assert [r[0] for r in cursor.fetchall()] == [bajo_en_sucursal_1]


def test_control_existencias_excluye_insumo_sin_minimo_configurado(cursor):
    insumo_id = _crear_insumo_simple(cursor)  # stock_minimo NULL
    cursor.execute(
        "SELECT id FROM vista_control_existencias WHERE id = %s", (insumo_id,)
    )
    assert cursor.fetchone() is None


def test_control_existencias_excluye_insumo_inactivo(cursor):
    insumo_id = _crear_insumo_simple(cursor, stock_minimo=10)
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))

    cursor.execute(
        "SELECT id FROM vista_control_existencias WHERE id = %s", (insumo_id,)
    )
    assert cursor.fetchone() is None


# --- próximos a vencer (RF-21, RF-22, RF-23, RF-34) ---

def test_proximos_a_vencer_incluye_insumo_dentro_del_rango(cursor):
    # Rango de alerta enorme a propósito: no depende de qué día se corra el
    # test, cualquier fecha de vencimiento futura cae dentro del rango.
    insumo_id = _crear_insumo_simple(
        cursor, fecha_vencimiento="2030-01-01", dias_alerta_vencimiento=999999
    )
    cursor.execute(
        "SELECT id FROM vista_proximos_a_vencer WHERE id = %s", (insumo_id,)
    )
    assert cursor.fetchone() == (insumo_id,)


def test_proximos_a_vencer_excluye_insumo_fuera_del_rango(cursor):
    insumo_id = _crear_insumo_simple(
        cursor, fecha_vencimiento="2099-01-01", dias_alerta_vencimiento=3
    )
    cursor.execute(
        "SELECT id FROM vista_proximos_a_vencer WHERE id = %s", (insumo_id,)
    )
    assert cursor.fetchone() is None


def test_proximos_a_vencer_excluye_insumo_sin_fecha_vencimiento(cursor):
    insumo_id = _crear_insumo_simple(cursor)  # fecha_vencimiento NULL
    cursor.execute(
        "SELECT id FROM vista_proximos_a_vencer WHERE id = %s", (insumo_id,)
    )
    assert cursor.fetchone() is None


def test_proximos_a_vencer_excluye_insumo_inactivo(cursor):
    insumo_id = _crear_insumo_simple(
        cursor, fecha_vencimiento="2030-01-01", dias_alerta_vencimiento=999999
    )
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))

    cursor.execute(
        "SELECT id FROM vista_proximos_a_vencer WHERE id = %s", (insumo_id,)
    )
    assert cursor.fetchone() is None


def test_proximos_a_vencer_usa_default_de_7_dias_si_no_esta_configurado(cursor):
    insumo_id = _crear_insumo_simple(cursor)
    # Vence en 3 días desde "hoy" (calculado en SQL, no hardcodeado) — cae
    # dentro del default de 7 sin necesidad de configurar dias_alerta_vencimiento.
    _set_usuario_actual(cursor, 1)
    cursor.execute(
        "UPDATE item_inventario SET fecha_vencimiento = CURRENT_DATE + 3 WHERE id = %s",
        (insumo_id,),
    )
    cursor.execute(
        "SELECT dias_alerta_aplicado FROM vista_proximos_a_vencer WHERE id = %s",
        (insumo_id,),
    )
    assert cursor.fetchone() == (7,)


# --- disponibilidad para Menú (RF-27, RF-35) ---

def test_disponibilidad_insumo_activo_con_stock_suficiente(cursor):
    insumo_id = _crear_insumo_simple(cursor)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=10)

    cursor.execute(
        "SELECT disponible FROM fn_verificar_disponibilidad(%s::jsonb)",
        (json.dumps([{"item_inventario_id": insumo_id, "cantidad_requerida": 5}]),),
    )
    assert cursor.fetchone() == (True,)


def test_disponibilidad_insumo_con_stock_insuficiente(cursor):
    insumo_id = _crear_insumo_simple(cursor)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=2)

    cursor.execute(
        "SELECT disponible FROM fn_verificar_disponibilidad(%s::jsonb)",
        (json.dumps([{"item_inventario_id": insumo_id, "cantidad_requerida": 5}]),),
    )
    assert cursor.fetchone() == (False,)


def test_disponibilidad_insumo_inactivo_siempre_false(cursor):
    insumo_id = _crear_insumo_simple(cursor)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=100)
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))

    cursor.execute(
        "SELECT disponible FROM fn_verificar_disponibilidad(%s::jsonb)",
        (json.dumps([{"item_inventario_id": insumo_id, "cantidad_requerida": 1}]),),
    )
    assert cursor.fetchone() == (False,)


def test_disponibilidad_varios_insumos_a_la_vez(cursor):
    disponible_id = _crear_insumo_simple(cursor, categoria_nombre="Lácteos", nombre="A")
    _crear_movimiento(cursor, disponible_id, "ENTRADA", cantidad_movimiento=10)
    insuficiente_id = _crear_insumo_simple(cursor, categoria_nombre="Cárnicos", nombre="B")
    _crear_movimiento(cursor, insuficiente_id, "ENTRADA", cantidad_movimiento=1)

    cursor.execute(
        "SELECT item_inventario_id, disponible FROM fn_verificar_disponibilidad(%s::jsonb) "
        "ORDER BY item_inventario_id",
        (json.dumps([
            {"item_inventario_id": disponible_id, "cantidad_requerida": 5},
            {"item_inventario_id": insuficiente_id, "cantidad_requerida": 5},
        ]),),
    )
    resultado = dict(cursor.fetchall())
    assert resultado == {disponible_id: True, insuficiente_id: False}


def test_disponibilidad_insumo_inexistente_se_reporta_no_disponible(cursor):
    # Verificación posterior (2026-09-23): el JOIN descartaba en silencio el
    # insumo desconocido, así que una receta con un ingrediente inexistente
    # parecía disponible completa.
    insumo_id = _crear_insumo_simple(cursor)
    _crear_movimiento(cursor, insumo_id, "ENTRADA", cantidad_movimiento=10)

    cursor.execute(
        "SELECT item_inventario_id, disponible FROM fn_verificar_disponibilidad(%s::jsonb) "
        "ORDER BY item_inventario_id",
        (json.dumps([
            {"item_inventario_id": insumo_id, "cantidad_requerida": 1},
            {"item_inventario_id": 999999999, "cantidad_requerida": 1},
        ]),),
    )
    assert cursor.fetchall() == [(insumo_id, True), (999999999, False)]
