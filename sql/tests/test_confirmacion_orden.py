import itertools

import psycopg2
import pytest

from test_item_inventario import _crear_insumo
from test_orden_compra import (
    ADMINISTRADOR, JEFE_ALMACEN, USUARIO_PROVEEDOR, _agregar_linea, _crear_orden, _estado,
    _proveedor_con_insumo, _registrar_insumo_suministrado, _transicion,
)


_ordenes = itertools.count(1)


def _orden_aprobada_con_dos_lineas(cursor):
    """Orden aprobada: 10 de leche (estimado 4200) y 4 de queso (estimado 9800).
    Nombres únicos, para poder armar varias órdenes en un mismo test."""
    n = next(_ordenes)
    proveedor_id, leche_id = _proveedor_con_insumo(cursor, precio_vigente=4200,
                                                   nombre_insumo=f"Leche entera {n}")
    cursor.execute("SELECT categoria_id FROM item_inventario WHERE id = %s", (leche_id,))
    queso_id = _crear_insumo(cursor, cursor.fetchone()[0], nombre=f"Queso crema {n}")
    _registrar_insumo_suministrado(cursor, proveedor_id, queso_id, precio_vigente=9800)
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_leche = _agregar_linea(cursor, orden_id, leche_id, cantidad=10)
    linea_queso = _agregar_linea(cursor, orden_id, queso_id, cantidad=4)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    _transicion(cursor, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
    return orden_id, linea_leche, linea_queso


def _informar(cursor, linea_id, disponibilidad, precio=None, motivo=None):
    cursor.execute(
        """
        UPDATE orden_compra_linea
        SET disponibilidad = %s, precio_confirmado = %s, motivo_no_disponible = %s
        WHERE id = %s
        """,
        (disponibilidad, precio, motivo, linea_id),
    )


def _agregar_fecha(cursor, orden_id, dias_desde_hoy=3):
    # "Hoy" es el de la base (CURRENT_DATE), no el de Python (Decisión #14).
    cursor.execute(
        """
        INSERT INTO orden_compra_fecha_entrega (orden_compra_id, fecha, usuario_id)
        VALUES (%s, CURRENT_DATE + %s, %s) RETURNING id
        """,
        (orden_id, dias_desde_hoy, USUARIO_PROVEEDOR),
    )
    return cursor.fetchone()[0]


def _orden_confirmada(cursor):
    orden_id, leche, queso = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    _informar(cursor, queso, "DISPONIBLE", precio=9500)
    _agregar_fecha(cursor, orden_id)
    _transicion(cursor, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)
    return orden_id, leche, queso


def _orden_confirmada_en_parte(cursor):
    orden_id, leche, queso = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    _informar(cursor, queso, "NO_DISPONIBLE", motivo="Agotado")
    _agregar_fecha(cursor, orden_id)
    _transicion(cursor, orden_id, "CONFIRMADA_PARCIAL", usuario_id=USUARIO_PROVEEDOR,
                motivo="Sin queso hasta el mes que viene")
    return orden_id, leche, queso


# --- confirmar (RF-21, RF-22, RF-24, RF-26, RF-32) ---

def test_confirmar_una_orden_completa_registra_usuario_y_fecha(cursor):
    orden_id, _, _ = _orden_confirmada(cursor)
    assert _estado(cursor, orden_id) == "CONFIRMADA"
    cursor.execute(
        """
        SELECT usuario_id, creado_en IS NOT NULL FROM orden_compra_transicion
        WHERE orden_compra_id = %s AND estado_nuevo = 'CONFIRMADA'
        """,
        (orden_id,),
    )
    assert cursor.fetchone() == (USUARIO_PROVEEDOR, True)


def test_confirmar_en_parte_con_observaciones_y_que_el_jefe_la_acepte(cursor):
    orden_id, _, _ = _orden_confirmada_en_parte(cursor)
    assert _estado(cursor, orden_id) == "CONFIRMADA_PARCIAL"
    _transicion(cursor, orden_id, "ACEPTADA_PARCIAL", usuario_id=JEFE_ALMACEN)
    assert _estado(cursor, orden_id) == "ACEPTADA_PARCIAL"
    cursor.execute(
        """
        SELECT estado_nuevo, usuario_id, motivo FROM orden_compra_transicion
        WHERE orden_compra_id = %s AND estado_nuevo IN ('CONFIRMADA_PARCIAL', 'ACEPTADA_PARCIAL')
        ORDER BY id
        """,
        (orden_id,),
    )
    assert cursor.fetchall() == [
        ("CONFIRMADA_PARCIAL", USUARIO_PROVEEDOR, "Sin queso hasta el mes que viene"),
        ("ACEPTADA_PARCIAL", JEFE_ALMACEN, None),
    ]


def test_rechaza_confirmacion_parcial_sin_observaciones(cursor):
    # RF-24 ("con observaciones") y CU-COM-03: el proveedor lo indica ahí.
    orden_id, leche, queso = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    _informar(cursor, queso, "NO_DISPONIBLE", motivo="Agotado")
    _agregar_fecha(cursor, orden_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _transicion(cursor, orden_id, "CONFIRMADA_PARCIAL", usuario_id=USUARIO_PROVEEDOR)


def test_aceptar_solo_una_confirmacion_parcial(cursor):
    orden_id, _, _ = _orden_confirmada(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "ACEPTADA_PARCIAL", usuario_id=JEFE_ALMACEN)


@pytest.mark.parametrize("preparar", [_orden_confirmada, _orden_confirmada_en_parte])
def test_una_orden_confirmada_se_puede_cancelar(cursor, preparar):
    # RF-19: sigue abierta. En la parcial, es lo que hace el Jefe si no la acepta.
    orden_id, _, _ = preparar(cursor)
    _transicion(cursor, orden_id, "CANCELADA", usuario_id=JEFE_ALMACEN, motivo="Se compra en otro lado")
    assert _estado(cursor, orden_id) == "CANCELADA"


# --- lo que no se puede confirmar ---

@pytest.mark.parametrize("estado_previo", ["PENDIENTE_APROBACION", "CANCELADA"])
def test_rechaza_informar_o_confirmar_una_orden_no_aprobada(cursor, estado_previo):
    # RF-20 (y RF-110: tampoco en un estado final).
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_id = _agregar_linea(cursor, orden_id, leche_id)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    if estado_previo == "CANCELADA":
        _transicion(cursor, orden_id, "CANCELADA", motivo="No va")

    cursor.execute("SAVEPOINT intento")
    with pytest.raises(psycopg2.errors.RaiseException):
        _informar(cursor, linea_id, "DISPONIBLE", precio=4300)
    cursor.execute("ROLLBACK TO SAVEPOINT intento")
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)


def test_rechaza_no_disponible_sin_motivo(cursor):
    # RF-23.
    _, leche, _ = _orden_aprobada_con_dos_lineas(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _informar(cursor, leche, "NO_DISPONIBLE")


def test_rechaza_precio_confirmado_negativo(cursor):
    # RF-27.
    _, leche, _ = _orden_aprobada_con_dos_lineas(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _informar(cursor, leche, "DISPONIBLE", precio=-1)


@pytest.mark.parametrize("destino", ["CONFIRMADA", "CONFIRMADA_PARCIAL"])
def test_rechaza_confirmar_con_un_insumo_pendiente(cursor, destino):
    # RF-86.
    orden_id, leche, _ = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    _agregar_fecha(cursor, orden_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, destino, usuario_id=USUARIO_PROVEEDOR, motivo="obs")


def test_rechaza_confirmar_con_un_disponible_sin_precio(cursor):
    # RF-28.
    orden_id, leche, queso = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    _informar(cursor, queso, "DISPONIBLE")
    _agregar_fecha(cursor, orden_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)


def test_rechaza_confirmar_sin_fecha_de_entrega(cursor):
    # RF-113.
    orden_id, leche, queso = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    _informar(cursor, queso, "DISPONIBLE", precio=9500)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)


@pytest.mark.parametrize("destino", ["CONFIRMADA", "CONFIRMADA_PARCIAL"])
def test_rechaza_confirmar_con_todo_no_disponible(cursor, destino):
    # RF-25: lo que corresponde es cancelarla.
    orden_id, leche, queso = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "NO_DISPONIBLE", motivo="Agotado")
    _informar(cursor, queso, "NO_DISPONIBLE", motivo="Descontinuado")
    _agregar_fecha(cursor, orden_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, destino, usuario_id=USUARIO_PROVEEDOR, motivo="obs")


def test_el_estado_de_confirmacion_tiene_que_coincidir_con_lo_informado(cursor):
    # "Confirmada" = todo disponible; "confirmada en parte" = algo no disponible.
    orden_id, leche, queso = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    _informar(cursor, queso, "NO_DISPONIBLE", motivo="Agotado")
    _agregar_fecha(cursor, orden_id)
    cursor.execute("SAVEPOINT intento")
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)
    cursor.execute("ROLLBACK TO SAVEPOINT intento")

    _informar(cursor, queso, "DISPONIBLE", precio=9500)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "CONFIRMADA_PARCIAL", usuario_id=USUARIO_PROVEEDOR, motivo="obs")


def test_rechaza_crear_una_linea_con_datos_de_confirmacion(cursor):
    # Disponibilidad y precio confirmado los informa el proveedor después.
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            """
            INSERT INTO orden_compra_linea
                (orden_compra_id, item_inventario_id, cantidad, disponibilidad, precio_confirmado)
            VALUES (%s, %s, 10, 'DISPONIBLE', 4300)
            """,
            (orden_id, leche_id),
        )


# --- fechas de entrega (RF-30, RF-31) ---

def test_rechaza_una_fecha_anterior_a_hoy_y_acepta_la_de_hoy(cursor):
    orden_id, _, _ = _orden_aprobada_con_dos_lineas(cursor)
    _agregar_fecha(cursor, orden_id, dias_desde_hoy=0)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_fecha(cursor, orden_id, dias_desde_hoy=-1)


def test_varias_fechas_de_entrega_por_orden(cursor):
    orden_id, _, _ = _orden_aprobada_con_dos_lineas(cursor)
    for dias in (2, 9, 16):
        _agregar_fecha(cursor, orden_id, dias_desde_hoy=dias)
    cursor.execute(
        "SELECT fecha - CURRENT_DATE FROM orden_compra_fecha_entrega WHERE orden_compra_id = %s ORDER BY fecha",
        (orden_id,),
    )
    assert [r[0] for r in cursor.fetchall()] == [2, 9, 16]


def test_rechaza_fechas_en_una_orden_no_aprobada(cursor):
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, leche_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_fecha(cursor, orden_id)


# --- congelado después de confirmar (RF-87) ---

@pytest.mark.parametrize("sentencia", [
    "UPDATE orden_compra_linea SET precio_confirmado = 1 WHERE orden_compra_id = %s",
    "UPDATE orden_compra_linea SET disponibilidad = 'PENDIENTE' WHERE orden_compra_id = %s",
    "INSERT INTO orden_compra_fecha_entrega (orden_compra_id, fecha, usuario_id) VALUES (%s, CURRENT_DATE + 30, 15)",
    "DELETE FROM orden_compra_fecha_entrega WHERE orden_compra_id = %s",
])
def test_congela_disponibilidad_precios_y_fechas_despues_de_confirmar(cursor, sentencia):
    orden_id, _, _ = _orden_confirmada(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (orden_id,))


# --- compatibilidad con guardados de fila completa (Django save(), spec 003) ---

def test_guardar_la_fila_completa_con_la_orden_aprobada_solo_cambia_la_confirmacion(cursor):
    # Un save() de Django manda todas las columnas: mencionar la cantidad sin
    # cambiarla no tiene que disparar la regla de "solo en borrador".
    _, leche, _ = _orden_aprobada_con_dos_lineas(cursor)
    cursor.execute(
        """
        UPDATE orden_compra_linea
        SET orden_compra_id = orden_compra_id, item_inventario_id = item_inventario_id,
            cantidad = cantidad, precio_estimado = precio_estimado,
            disponibilidad = 'DISPONIBLE', precio_confirmado = 4300, motivo_no_disponible = NULL
        WHERE id = %s
        """,
        (leche,),
    )
    cursor.execute("SELECT disponibilidad, precio_confirmado FROM orden_compra_linea WHERE id = %s", (leche,))
    assert cursor.fetchone() == ("DISPONIBLE", 4300)


def test_guardar_la_fila_completa_en_borrador_solo_cambia_la_cantidad(cursor):
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_id = _agregar_linea(cursor, orden_id, leche_id, cantidad=10)
    cursor.execute(
        """
        UPDATE orden_compra_linea
        SET cantidad = 12, disponibilidad = disponibilidad,
            precio_confirmado = precio_confirmado, motivo_no_disponible = motivo_no_disponible
        WHERE id = %s
        """,
        (linea_id,),
    )
    cursor.execute("SELECT cantidad FROM orden_compra_linea WHERE id = %s", (linea_id,))
    assert cursor.fetchone() == (12,)


# --- valor confirmado (RF-29) ---

def _valor_confirmado(cursor, orden_id):
    cursor.execute("SELECT valor_confirmado FROM vista_orden_compra_resumen WHERE id = %s", (orden_id,))
    return cursor.fetchone()[0]


def test_valor_confirmado_queda_desconocido_hasta_confirmar(cursor):
    orden_id, leche, _ = _orden_aprobada_con_dos_lineas(cursor)
    _informar(cursor, leche, "DISPONIBLE", precio=4300)
    assert _valor_confirmado(cursor, orden_id) is None


def test_valor_confirmado_de_una_orden_completa(cursor):
    # 10 x 4300 + 4 x 9500 = 43000 + 38000.
    orden_id, _, _ = _orden_confirmada(cursor)
    assert _valor_confirmado(cursor, orden_id) == 81000


def test_valor_confirmado_de_una_orden_en_parte_cuenta_solo_lo_disponible(cursor):
    # Solo la leche: 10 x 4300.
    orden_id, _, _ = _orden_confirmada_en_parte(cursor)
    assert _valor_confirmado(cursor, orden_id) == 43000
