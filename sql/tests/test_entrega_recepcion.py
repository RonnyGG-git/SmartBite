import threading
import time

import psycopg2
import pytest

from test_confirmacion_orden import (
    _agregar_fecha, _informar, _orden_aprobada_con_dos_lineas, _orden_confirmada,
    _orden_confirmada_en_parte,
)
from test_item_inventario import _crear_categoria, _crear_insumo
from test_orden_compra import (
    ADMINISTRADOR, JEFE_ALMACEN, USUARIO_PROVEEDOR, _agregar_linea, _crear_orden, _estado,
    _transicion,
)
from test_proveedor import _crear_proveedor, _registrar_insumo_suministrado


def _registrar_entrega(cursor, orden_id, lineas=(), usuario_id=USUARIO_PROVEEDOR):
    """lineas: pares (orden_compra_linea_id, cantidad_entregada)."""
    cursor.execute(
        "INSERT INTO entrega (orden_compra_id, registrada_por) VALUES (%s, %s) RETURNING id",
        (orden_id, usuario_id),
    )
    entrega_id = cursor.fetchone()[0]
    for linea_id, cantidad in lineas:
        _agregar_linea_entregada(cursor, entrega_id, linea_id, cantidad)
    return entrega_id


def _agregar_linea_entregada(cursor, entrega_id, linea_id, cantidad):
    cursor.execute(
        """
        INSERT INTO entrega_linea (entrega_id, orden_compra_linea_id, cantidad_entregada)
        VALUES (%s, %s, %s) RETURNING id
        """,
        (entrega_id, linea_id, cantidad),
    )
    return cursor.fetchone()[0]


def _anular_entrega(cursor, entrega_id, usuario_id=USUARIO_PROVEEDOR, motivo="Cargada por error"):
    cursor.execute(
        "UPDATE entrega SET anulada_por = %s, motivo_anulacion = %s WHERE id = %s",
        (usuario_id, motivo, entrega_id),
    )


def _orden_aceptada_en_parte(cursor):
    orden_id, leche, queso = _orden_confirmada_en_parte(cursor)
    _transicion(cursor, orden_id, "ACEPTADA_PARCIAL", usuario_id=JEFE_ALMACEN)
    return orden_id, leche, queso


# --- registrar entregas (RF-34, RF-35, RF-46) ---

def test_registrar_una_entrega_con_usuario_y_fecha_pasa_la_orden_a_en_recepcion(cursor):
    orden_id, leche, queso = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id, [(leche, 10), (queso, 4)])

    cursor.execute(
        "SELECT registrada_por, registrada_en IS NOT NULL FROM entrega WHERE id = %s", (entrega_id,)
    )
    assert cursor.fetchone() == (USUARIO_PROVEEDOR, True)
    cursor.execute(
        "SELECT orden_compra_linea_id, cantidad_entregada FROM entrega_linea "
        "WHERE entrega_id = %s ORDER BY orden_compra_linea_id",
        (entrega_id,),
    )
    assert cursor.fetchall() == [(leche, 10), (queso, 4)]
    assert _estado(cursor, orden_id) == "EN_RECEPCION"
    cursor.execute(
        """
        SELECT estado_anterior, usuario_id FROM orden_compra_transicion
        WHERE orden_compra_id = %s AND estado_nuevo = 'EN_RECEPCION'
        """,
        (orden_id,),
    )
    assert cursor.fetchone() == ("CONFIRMADA", USUARIO_PROVEEDOR)


def test_una_entrega_sin_insumos_no_cambia_el_estado(cursor):
    # "En recepción" = tiene entregas registradas; una vacía no trajo nada.
    orden_id, _, _ = _orden_confirmada(cursor)
    _registrar_entrega(cursor, orden_id)
    assert _estado(cursor, orden_id) == "CONFIRMADA"


def test_varias_entregas_de_la_misma_orden(cursor):
    orden_id, leche, queso = _orden_confirmada(cursor)
    _registrar_entrega(cursor, orden_id, [(leche, 6)])
    _registrar_entrega(cursor, orden_id, [(leche, 4), (queso, 4)])

    cursor.execute("SELECT count(*) FROM entrega WHERE orden_compra_id = %s", (orden_id,))
    assert cursor.fetchone() == (2,)
    cursor.execute(
        "SELECT count(*) FROM orden_compra_transicion "
        "WHERE orden_compra_id = %s AND estado_nuevo = 'EN_RECEPCION'",
        (orden_id,),
    )
    assert cursor.fetchone() == (1,)  # pasa a en recepción una sola vez
    assert _estado(cursor, orden_id) == "EN_RECEPCION"


def test_entregar_una_orden_aceptada_en_parte(cursor):
    orden_id, leche, _ = _orden_aceptada_en_parte(cursor)
    _registrar_entrega(cursor, orden_id, [(leche, 10)])
    assert _estado(cursor, orden_id) == "EN_RECEPCION"


# --- cuándo no se puede entregar (RF-33, RF-110) ---

def _aprobada(cursor):
    return _orden_aprobada_con_dos_lineas(cursor)


def _confirmada_en_parte_sin_aceptar(cursor):
    return _orden_confirmada_en_parte(cursor)


def _cancelada(cursor):
    orden_id, leche, queso = _orden_confirmada(cursor)
    _transicion(cursor, orden_id, "CANCELADA", usuario_id=JEFE_ALMACEN, motivo="Ya no hace falta")
    return orden_id, leche, queso


@pytest.mark.parametrize("preparar", [_aprobada, _confirmada_en_parte_sin_aceptar, _cancelada])
def test_rechaza_entregar_en_una_orden_que_no_lo_admite(cursor, preparar):
    orden_id, _, _ = preparar(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _registrar_entrega(cursor, orden_id)


def test_rechaza_entregar_un_insumo_no_disponible(cursor):
    # RF-88: lo que llegue de más queda como discrepancia, no como entrega.
    orden_id, leche, queso = _orden_aceptada_en_parte(cursor)  # el queso no estaba disponible
    entrega_id = _registrar_entrega(cursor, orden_id, [(leche, 10)])
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea_entregada(cursor, entrega_id, queso, 4)


def test_rechaza_una_linea_de_otra_orden(cursor):
    orden_a, leche_a, _ = _orden_confirmada(cursor)
    orden_b, leche_b, _ = _orden_confirmada(cursor)
    entrega_a = _registrar_entrega(cursor, orden_a)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea_entregada(cursor, entrega_a, leche_b, 1)


@pytest.mark.parametrize("cantidad", [0, -2])
def test_rechaza_cantidad_entregada_cero_o_negativa(cursor, cantidad):
    # RF-89.
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _agregar_linea_entregada(cursor, entrega_id, leche, cantidad)


# --- discrepancias (RF-38) ---

def test_registrar_una_discrepancia(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id, [(leche, 10)])
    cursor.execute(
        """
        INSERT INTO entrega_discrepancia (entrega_id, descripcion, usuario_id)
        VALUES (%s, 'Llegaron 2 cajas de yogur que no se pidieron', %s) RETURNING id
        """,
        (entrega_id, JEFE_ALMACEN),
    )
    discrepancia_id = cursor.fetchone()[0]
    cursor.execute(
        "SELECT usuario_id, creado_en IS NOT NULL FROM entrega_discrepancia WHERE id = %s",
        (discrepancia_id,),
    )
    assert cursor.fetchone() == (JEFE_ALMACEN, True)


@pytest.mark.parametrize("descripcion", ["", "   "])
def test_rechaza_una_discrepancia_en_blanco(cursor, descripcion):
    orden_id, _, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        cursor.execute(
            "INSERT INTO entrega_discrepancia (entrega_id, descripcion, usuario_id) VALUES (%s, %s, %s)",
            (entrega_id, descripcion, JEFE_ALMACEN),
        )


# --- anulación (RF-91) ---

def test_anular_una_entrega_con_motivo(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id, [(leche, 10)])
    _anular_entrega(cursor, entrega_id)
    cursor.execute(
        "SELECT anulada_por, anulada_en IS NOT NULL, motivo_anulacion FROM entrega WHERE id = %s",
        (entrega_id,),
    )
    assert cursor.fetchone() == (USUARIO_PROVEEDOR, True, "Cargada por error")


def test_rechaza_anular_sin_motivo(cursor):
    orden_id, _, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _anular_entrega(cursor, entrega_id, motivo=None)


def test_rechaza_anular_dos_veces(cursor):
    orden_id, _, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id)
    _anular_entrega(cursor, entrega_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _anular_entrega(cursor, entrega_id, motivo="Otra vez")


def test_rechaza_agregar_insumos_a_una_entrega_anulada(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id)
    _anular_entrega(cursor, entrega_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea_entregada(cursor, entrega_id, leche, 10)


@pytest.mark.parametrize("sentencia", [
    "UPDATE entrega SET registrada_por = 99 WHERE id = %s",
    "DELETE FROM entrega WHERE id = %s",
    "UPDATE entrega_linea SET cantidad_entregada = 1 WHERE entrega_id = %s",
    "DELETE FROM entrega_linea WHERE entrega_id = %s",
])
def test_una_entrega_no_se_edita_ni_se_borra(cursor, sentencia):
    # Requisito no funcional: una entrega solo se anula.
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id, [(leche, 10)])
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (entrega_id,))


def test_las_discrepancias_no_se_editan_ni_se_borran(cursor):
    orden_id, _, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id)
    cursor.execute(
        "INSERT INTO entrega_discrepancia (entrega_id, descripcion, usuario_id) VALUES (%s, 'Caja golpeada', 7)",
        (entrega_id,),
    )
    for sentencia in ("UPDATE entrega_discrepancia SET descripcion = 'otra' WHERE entrega_id = %s",
                      "DELETE FROM entrega_discrepancia WHERE entrega_id = %s"):
        cursor.execute("SAVEPOINT intento")
        with pytest.raises(psycopg2.errors.RaiseException):
            cursor.execute(sentencia, (entrega_id,))
        cursor.execute("ROLLBACK TO SAVEPOINT intento")


# --- cancelar anula las entregas sin recibir (RF-111) ---

def test_cancelar_una_orden_anula_sus_entregas_sin_recibir(cursor):
    orden_id, leche, queso = _orden_confirmada(cursor)
    primera = _registrar_entrega(cursor, orden_id, [(leche, 6)])
    segunda = _registrar_entrega(cursor, orden_id, [(queso, 4)])
    _transicion(cursor, orden_id, "CANCELADA", usuario_id=JEFE_ALMACEN, motivo="El proveedor no cumple")

    cursor.execute(
        """
        SELECT id, anulada_por, motivo_anulacion LIKE '%%cancelada%%El proveedor no cumple%%'
        FROM entrega WHERE orden_compra_id = %s ORDER BY id
        """,
        (orden_id,),
    )
    assert cursor.fetchall() == [(primera, JEFE_ALMACEN, True), (segunda, JEFE_ALMACEN, True)]


def test_dos_entregas_simultaneas_de_la_misma_orden_no_se_traban(esquema, database_url):
    # Con FOR SHARE sobre la orden, las dos se bloqueaban entre sí al pasar a
    # EN_RECEPCION y una moría por deadlock (verificado con una mutación).
    setup = psycopg2.connect(database_url)
    setup.autocommit = True
    with setup.cursor() as cur:
        categoria_id = _crear_categoria(cur, nombre="Concurrencia entregas")
        proveedor_id = _crear_proveedor(cur, nit="343434343", nombre="Proveedor entregas")
        insumo_id = _crear_insumo(cur, categoria_id, sucursal_id=994, nombre="Insumo entregas")
        _registrar_insumo_suministrado(cur, proveedor_id, insumo_id, precio_vigente=10)
        orden_id = _crear_orden(cur, proveedor_id, sucursal_id=994)
        linea_id = _agregar_linea(cur, orden_id, insumo_id, cantidad=10)
        _transicion(cur, orden_id, "PENDIENTE_APROBACION")
        _transicion(cur, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
        _informar(cur, linea_id, "DISPONIBLE", precio=10)
        _agregar_fecha(cur, orden_id)
        _transicion(cur, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)
    setup.close()

    barrera = threading.Barrier(2)
    resultados = []

    def entregar():
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                barrera.wait()
                entrega_id = _registrar_entrega(cur, orden_id)
                time.sleep(0.5)
                _agregar_linea_entregada(cur, entrega_id, linea_id, 5)
            conn.commit()
            resultados.append("OK")
        except psycopg2.Error as error:
            conn.rollback()
            resultados.append(type(error).__name__)
        finally:
            conn.close()

    hilos = [threading.Thread(target=entregar) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert resultados == ["OK", "OK"]
    verificar = psycopg2.connect(database_url)
    with verificar.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM orden_compra_transicion "
            "WHERE orden_compra_id = %s AND estado_nuevo = 'EN_RECEPCION'",
            (orden_id,),
        )
        assert cur.fetchone() == (1,)
    verificar.close()


def test_cancelar_no_vuelve_a_anular_una_entrega_ya_anulada(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id = _registrar_entrega(cursor, orden_id, [(leche, 10)])
    _anular_entrega(cursor, entrega_id, motivo="Cargada por error")
    _transicion(cursor, orden_id, "CANCELADA", usuario_id=JEFE_ALMACEN, motivo="No va")
    cursor.execute("SELECT anulada_por, motivo_anulacion FROM entrega WHERE id = %s", (entrega_id,))
    assert cursor.fetchone() == (USUARIO_PROVEEDOR, "Cargada por error")


# --- recepción (T9) ---

def _entrega_con_lineas(cursor, orden_id, lineas):
    """lineas: pares (orden_compra_linea_id, cantidad). Devuelve la entrega y
    los id de sus líneas, en el mismo orden."""
    entrega_id = _registrar_entrega(cursor, orden_id)
    return entrega_id, [_agregar_linea_entregada(cursor, entrega_id, linea, cantidad)
                        for linea, cantidad in lineas]


def _recibir(cursor, entrega_id, lineas=(), usuario_id=JEFE_ALMACEN):
    """lineas: pares (entrega_linea_id, cantidad_recibida) o ternas con los
    días hasta el vencimiento, contados desde el CURRENT_DATE de la base."""
    cursor.execute(
        "INSERT INTO recepcion (entrega_id, usuario_id) VALUES (%s, %s) RETURNING id",
        (entrega_id, usuario_id),
    )
    recepcion_id = cursor.fetchone()[0]
    for linea in lineas:
        entrega_linea_id, cantidad = linea[0], linea[1]
        dias = linea[2] if len(linea) > 2 else None
        _agregar_linea_recibida(cursor, recepcion_id, entrega_linea_id, cantidad, dias)
    return recepcion_id


def _agregar_linea_recibida(cursor, recepcion_id, entrega_linea_id, cantidad, dias_vencimiento=None):
    cursor.execute(
        """
        INSERT INTO recepcion_linea (recepcion_id, entrega_linea_id, cantidad_recibida, fecha_vencimiento)
        VALUES (%s, %s, %s, CURRENT_DATE + %s::integer) RETURNING id
        """,
        (recepcion_id, entrega_linea_id, cantidad, dias_vencimiento),
    )
    return cursor.fetchone()[0]


def test_confirmar_la_recepcion_con_cantidades_y_vencimiento(cursor):
    # RF-36 y RF-92: llegan 8 de las 10 de leche; el queso completo.
    orden_id, leche, queso = _orden_confirmada(cursor)
    entrega_id, (el_leche, el_queso) = _entrega_con_lineas(cursor, orden_id, [(leche, 10), (queso, 4)])
    recepcion_id = _recibir(cursor, entrega_id, [(el_leche, 8, 20), (el_queso, 4, 45)])

    cursor.execute(
        "SELECT usuario_id, creado_en IS NOT NULL FROM recepcion WHERE id = %s", (recepcion_id,)
    )
    assert cursor.fetchone() == (JEFE_ALMACEN, True)
    cursor.execute(
        """
        SELECT entrega_linea_id, cantidad_recibida, fecha_vencimiento - CURRENT_DATE
        FROM recepcion_linea WHERE recepcion_id = %s ORDER BY entrega_linea_id
        """,
        (recepcion_id,),
    )
    assert cursor.fetchall() == [(el_leche, 8, 20), (el_queso, 4, 45)]


def test_lo_recibido_puede_diferir_de_lo_que_registro_el_proveedor(cursor):
    # Se guarda lo que llegó; la diferencia se explica como discrepancia (RF-38).
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 5)])
    recepcion_id = _recibir(cursor, entrega_id, [(el_leche, 6)])
    cursor.execute("SELECT cantidad_recibida FROM recepcion_linea WHERE recepcion_id = %s", (recepcion_id,))
    assert cursor.fetchone() == (6,)


def test_una_cantidad_recibida_de_cero_es_valida(cursor):
    # RF-90 rechaza solo las negativas.
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 5)])
    _recibir(cursor, entrega_id, [(el_leche, 0)])


def test_rechaza_una_cantidad_recibida_negativa(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 5)])
    with pytest.raises(psycopg2.errors.CheckViolation):
        _recibir(cursor, entrega_id, [(el_leche, -1)])


def test_rechaza_una_segunda_recepcion_de_la_misma_entrega(cursor):
    # RF-37.
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    _recibir(cursor, entrega_id, [(el_leche, 10)])
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _recibir(cursor, entrega_id)


def test_rechaza_recibir_dos_veces_la_misma_linea(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    recepcion_id = _recibir(cursor, entrega_id, [(el_leche, 10)])
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _agregar_linea_recibida(cursor, recepcion_id, el_leche, 2)


def test_rechaza_recibir_una_entrega_anulada(cursor):
    # RF-115.
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, _ = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    _anular_entrega(cursor, entrega_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _recibir(cursor, entrega_id)


def test_rechaza_recibir_una_entrega_sin_insumos(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    _entrega_con_lineas(cursor, orden_id, [(leche, 10)])  # la orden queda en recepción
    vacia = _registrar_entrega(cursor, orden_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _recibir(cursor, vacia)


def test_rechaza_recibir_en_una_orden_en_estado_final(cursor):
    # RF-110. Al cancelar, las entregas sin recibir quedan anuladas; la
    # regla del estado final corta antes, con su propio mensaje.
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, _ = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    _transicion(cursor, orden_id, "CANCELADA", usuario_id=JEFE_ALMACEN, motivo="No va")
    with pytest.raises(psycopg2.errors.RaiseException, match="no admite recepciones"):
        _recibir(cursor, entrega_id)


def test_rechaza_una_linea_de_otra_entrega(cursor):
    orden_id, leche, queso = _orden_confirmada(cursor)
    primera, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    segunda, (el_queso,) = _entrega_con_lineas(cursor, orden_id, [(queso, 4)])
    recepcion_id = _recibir(cursor, primera)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea_recibida(cursor, recepcion_id, el_queso, 4)


def test_rechaza_anular_una_entrega_ya_recibida(cursor):
    # RF-91: se anula solo mientras la recepción no está confirmada.
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    _recibir(cursor, entrega_id, [(el_leche, 10)])
    with pytest.raises(psycopg2.errors.RaiseException):
        _anular_entrega(cursor, entrega_id)


def test_rechaza_agregar_insumos_a_una_entrega_ya_recibida(cursor):
    orden_id, leche, queso = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    _recibir(cursor, entrega_id, [(el_leche, 10)])
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea_entregada(cursor, entrega_id, queso, 4)


def test_rechaza_cancelar_una_orden_con_alguna_recepcion(cursor):
    # RF-85: para un faltante definitivo está el cierre con faltantes (T11).
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 4)])
    _recibir(cursor, entrega_id, [(el_leche, 4)])
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "CANCELADA", usuario_id=JEFE_ALMACEN, motivo="Ya no hace falta")


@pytest.mark.parametrize("sentencia", [
    "UPDATE recepcion SET usuario_id = 99 WHERE entrega_id = %s",
    "DELETE FROM recepcion WHERE entrega_id = %s",
    "UPDATE recepcion_linea SET cantidad_recibida = 1 WHERE recepcion_id = (SELECT id FROM recepcion WHERE entrega_id = %s)",
    "DELETE FROM recepcion_linea WHERE recepcion_id = (SELECT id FROM recepcion WHERE entrega_id = %s)",
])
def test_una_recepcion_no_se_edita_ni_se_borra(cursor, sentencia):
    orden_id, leche, _ = _orden_confirmada(cursor)
    entrega_id, (el_leche,) = _entrega_con_lineas(cursor, orden_id, [(leche, 10)])
    _recibir(cursor, entrega_id, [(el_leche, 10)])
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (entrega_id,))


def test_dos_recepciones_simultaneas_de_la_misma_entrega(esquema, database_url):
    # RF-37 ante concurrencia: el UNIQUE deja pasar una sola.
    setup = psycopg2.connect(database_url)
    setup.autocommit = True
    with setup.cursor() as cur:
        categoria_id = _crear_categoria(cur, nombre="Concurrencia RF-37")
        proveedor_id = _crear_proveedor(cur, nit="373737373", nombre="Proveedor RF-37")
        insumo_id = _crear_insumo(cur, categoria_id, sucursal_id=993, nombre="Insumo RF-37")
        _registrar_insumo_suministrado(cur, proveedor_id, insumo_id, precio_vigente=10)
        orden_id = _crear_orden(cur, proveedor_id, sucursal_id=993)
        linea_id = _agregar_linea(cur, orden_id, insumo_id, cantidad=10)
        _transicion(cur, orden_id, "PENDIENTE_APROBACION")
        _transicion(cur, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
        _informar(cur, linea_id, "DISPONIBLE", precio=10)
        _agregar_fecha(cur, orden_id)
        _transicion(cur, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)
        entrega_id, _ = _entrega_con_lineas(cur, orden_id, [(linea_id, 10)])
    setup.close()

    barrera = threading.Barrier(2)
    resultados = []

    def recibir():
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                barrera.wait()
                _recibir(cur, entrega_id)
                time.sleep(0.5)
            conn.commit()
            resultados.append("OK")
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            resultados.append("RECHAZADO")
        finally:
            conn.close()

    hilos = [threading.Thread(target=recibir) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["OK", "RECHAZADO"]
