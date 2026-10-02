import threading
import time

import psycopg2
import pytest

from test_confirmacion_orden import _agregar_fecha, _informar, _orden_confirmada
from test_entrega_recepcion import _agregar_linea_recibida, _entrega_con_lineas, _recibir
from test_item_inventario import _crear_categoria, _crear_insumo
from test_orden_compra import (
    ADMINISTRADOR, JEFE_ALMACEN, USUARIO_PROVEEDOR, _agregar_linea, _crear_orden, _transicion,
)
from test_proveedor import _crear_proveedor, _registrar_insumo_suministrado


def _insumo_de(cursor, linea_orden_id):
    cursor.execute("SELECT item_inventario_id FROM orden_compra_linea WHERE id = %s", (linea_orden_id,))
    return cursor.fetchone()[0]


def _stock(cursor, item_id):
    cursor.execute("SELECT stock_actual FROM item_inventario WHERE id = %s", (item_id,))
    return cursor.fetchone()[0]


def _entregar_y_recibir(cursor, orden_id, linea_orden_id, entregado, recibido):
    """Una entrega de un insumo, recibida. Devuelve el id de la línea recibida."""
    entrega_id, (entrega_linea,) = _entrega_con_lineas(cursor, orden_id, [(linea_orden_id, entregado)])
    recepcion_id = _recibir(cursor, entrega_id)
    return _agregar_linea_recibida(cursor, recepcion_id, entrega_linea, recibido)


def _leche_recibida(cursor, recibido=10):
    """Orden confirmada (10 de leche, 4 de queso) con la leche entregada y
    recibida. Devuelve (orden, línea de orden de la leche, línea recibida, insumo)."""
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=recibido, recibido=recibido)
    return orden_id, leche, recepcion_linea, _insumo_de(cursor, leche)


def _verificar(cursor, recepcion_linea_id, aprobada=0, rechazada=0, cuarentena=0,
               desde_cuarentena=False, usuario_id=JEFE_ALMACEN):
    cursor.execute(
        """
        INSERT INTO verificacion_calidad
            (recepcion_linea_id, cantidad_aprobada, cantidad_rechazada, cantidad_cuarentena,
             desde_cuarentena, usuario_id)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (recepcion_linea_id, aprobada, rechazada, cuarentena, desde_cuarentena, usuario_id),
    )
    return cursor.fetchone()[0]


# --- aprobar: la entrada al stock (RF-42) ---

def test_aprobar_genera_la_entrada_en_el_kardex_y_suma_stock(cursor):
    orden_id, _, recepcion_linea, insumo = _leche_recibida(cursor)
    verificacion_id = _verificar(cursor, recepcion_linea, aprobada=10)

    assert _stock(cursor, insumo) == 10
    cursor.execute(
        """
        SELECT m.tipo, m.cantidad_movimiento, m.compra_id, m.usuario_id, m.stock_anterior, m.stock_nuevo
        FROM verificacion_calidad v JOIN movimiento_inventario m ON m.id = v.movimiento_inventario_id
        WHERE v.id = %s
        """,
        (verificacion_id,),
    )
    assert cursor.fetchone() == ("ENTRADA", 10, orden_id, JEFE_ALMACEN, 0, 10)


def test_dividir_en_aprobado_rechazado_y_cuarentena(cursor):
    # RF-39, RF-40: solo lo aprobado entra al stock.
    _, _, recepcion_linea, insumo = _leche_recibida(cursor)
    verificacion_id = _verificar(cursor, recepcion_linea, aprobada=6, rechazada=2, cuarentena=2)
    assert _stock(cursor, insumo) == 6
    cursor.execute(
        """
        SELECT m.cantidad_movimiento FROM verificacion_calidad v
        JOIN movimiento_inventario m ON m.id = v.movimiento_inventario_id WHERE v.id = %s
        """,
        (verificacion_id,),
    )
    assert cursor.fetchone() == (6,)


def test_lo_rechazado_y_lo_que_esta_en_cuarentena_no_suman_stock(cursor):
    # RF-43: sin aprobado no hay movimiento.
    _, _, recepcion_linea, insumo = _leche_recibida(cursor)
    verificacion_id = _verificar(cursor, recepcion_linea, rechazada=4, cuarentena=6)
    assert _stock(cursor, insumo) == 0
    cursor.execute(
        "SELECT movimiento_inventario_id FROM verificacion_calidad WHERE id = %s", (verificacion_id,)
    )
    assert cursor.fetchone() == (None,)
    cursor.execute("SELECT count(*) FROM movimiento_inventario WHERE item_inventario_id = %s", (insumo,))
    assert cursor.fetchone() == (0,)


def test_resolver_una_cuarentena(cursor):
    # RF-44: lo que sale de cuarentena se trata igual que una verificación normal.
    _, _, recepcion_linea, insumo = _leche_recibida(cursor)
    _verificar(cursor, recepcion_linea, aprobada=6, cuarentena=4)
    _verificar(cursor, recepcion_linea, aprobada=3, rechazada=1, desde_cuarentena=True)
    assert _stock(cursor, insumo) == 9
    cursor.execute(
        "SELECT cantidad_movimiento FROM movimiento_inventario WHERE item_inventario_id = %s ORDER BY id",
        (insumo,),
    )
    assert [r[0] for r in cursor.fetchall()] == [6, 3]


# --- lo que no se puede verificar ---

def test_rechaza_una_suma_mayor_a_lo_recibido(cursor):
    # RF-41: se recibieron 8.
    _, _, recepcion_linea, _ = _leche_recibida(cursor, recibido=8)
    with pytest.raises(psycopg2.errors.RaiseException):
        _verificar(cursor, recepcion_linea, aprobada=6, rechazada=3)


def test_rechaza_una_suma_mayor_a_lo_recibido_en_varias_verificaciones(cursor):
    _, _, recepcion_linea, _ = _leche_recibida(cursor, recibido=8)
    _verificar(cursor, recepcion_linea, aprobada=5)
    with pytest.raises(psycopg2.errors.RaiseException):
        _verificar(cursor, recepcion_linea, rechazada=4)


def test_rechaza_aprobar_mas_que_lo_pendiente(cursor):
    # RF-114: se confirmaron 10 y el proveedor trajo 12; el exceso se rechaza.
    _, _, recepcion_linea, _ = _leche_recibida(cursor, recibido=12)
    cursor.execute("SAVEPOINT intento")
    with pytest.raises(psycopg2.errors.RaiseException):
        _verificar(cursor, recepcion_linea, aprobada=12)
    cursor.execute("ROLLBACK TO SAVEPOINT intento")
    _verificar(cursor, recepcion_linea, aprobada=10, rechazada=2)


def test_rechaza_aprobar_mas_que_lo_pendiente_entre_entregas(cursor):
    orden_id, leche, primera, _ = _leche_recibida(cursor, recibido=10)
    _verificar(cursor, primera, aprobada=10)
    segunda = _entregar_y_recibir(cursor, orden_id, leche, entregado=2, recibido=2)
    with pytest.raises(psycopg2.errors.RaiseException):
        _verificar(cursor, segunda, aprobada=2)


def test_rechaza_poner_en_cuarentena_mas_de_lo_que_se_puede_reservar(cursor):
    # Decisión #7: lo que está en cuarentena reserva pendiente. De 10
    # confirmados: 4 aprobados y 6 en cuarentena ya cubren todo.
    orden_id, leche, primera, _ = _leche_recibida(cursor, recibido=10)
    _verificar(cursor, primera, aprobada=4, cuarentena=6)
    segunda = _entregar_y_recibir(cursor, orden_id, leche, entregado=3, recibido=3)
    for cantidades in ({"aprobada": 1}, {"cuarentena": 1}):
        cursor.execute("SAVEPOINT intento")
        with pytest.raises(psycopg2.errors.RaiseException):
            _verificar(cursor, segunda, **cantidades)
        cursor.execute("ROLLBACK TO SAVEPOINT intento")
    _verificar(cursor, segunda, rechazada=3)  # rechazarlo sí se puede


def test_rechaza_resolver_mas_de_lo_que_hay_en_cuarentena(cursor):
    _, _, recepcion_linea, _ = _leche_recibida(cursor)
    _verificar(cursor, recepcion_linea, aprobada=7, cuarentena=3)
    with pytest.raises(psycopg2.errors.RaiseException):
        _verificar(cursor, recepcion_linea, aprobada=4, desde_cuarentena=True)


def test_una_resolucion_de_cuarentena_no_pone_mas_en_cuarentena(cursor):
    _, _, recepcion_linea, _ = _leche_recibida(cursor)
    _verificar(cursor, recepcion_linea, cuarentena=5)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _verificar(cursor, recepcion_linea, aprobada=2, cuarentena=1, desde_cuarentena=True)


def test_rechaza_una_verificacion_vacia(cursor):
    _, _, recepcion_linea, _ = _leche_recibida(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _verificar(cursor, recepcion_linea)


@pytest.mark.parametrize("cantidades", [
    {"aprobada": -1, "rechazada": 2},
    {"aprobada": 5, "rechazada": -1},
    {"aprobada": 5, "cuarentena": -1},
])
def test_rechaza_cantidades_negativas(cursor, cantidades):
    # RF-90.
    _, _, recepcion_linea, _ = _leche_recibida(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _verificar(cursor, recepcion_linea, **cantidades)


def test_el_movimiento_de_la_verificacion_lo_pone_la_base(cursor):
    _, _, recepcion_linea, insumo = _leche_recibida(cursor)
    cursor.execute(
        "INSERT INTO movimiento_inventario (item_inventario_id, tipo, cantidad_movimiento, usuario_id) "
        "VALUES (%s, 'ENTRADA', 1, 1) RETURNING id",
        (insumo,),
    )
    ajeno = cursor.fetchone()[0]
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            """
            INSERT INTO verificacion_calidad (recepcion_linea_id, cantidad_rechazada, movimiento_inventario_id, usuario_id)
            VALUES (%s, 1, %s, %s)
            """,
            (recepcion_linea, ajeno, JEFE_ALMACEN),
        )


@pytest.mark.parametrize("sentencia", [
    "UPDATE verificacion_calidad SET cantidad_aprobada = 1 WHERE id = %s",
    "DELETE FROM verificacion_calidad WHERE id = %s",
])
def test_una_verificacion_no_se_edita_ni_se_borra(cursor, sentencia):
    _, _, recepcion_linea, _ = _leche_recibida(cursor)
    verificacion_id = _verificar(cursor, recepcion_linea, aprobada=10)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (verificacion_id,))


def test_la_fk_de_compra_del_kardex_rechaza_una_orden_inexistente(cursor):
    # Decisión #3: compra_id ya es una FK real hacia orden_compra.
    _, _, _, insumo = _leche_recibida(cursor)
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cursor.execute(
            "INSERT INTO movimiento_inventario (item_inventario_id, tipo, cantidad_movimiento, compra_id, usuario_id) "
            "VALUES (%s, 'ENTRADA', 1, 999999999, 1)",
            (insumo,),
        )


# --- concurrencia (RF-93) ---

def test_dos_verificaciones_simultaneas_no_generan_dos_entradas(esquema, database_url):
    setup = psycopg2.connect(database_url)
    setup.autocommit = True
    with setup.cursor() as cur:
        categoria_id = _crear_categoria(cur, nombre="Concurrencia RF-93")
        proveedor_id = _crear_proveedor(cur, nit="939393939", nombre="Proveedor RF-93")
        insumo_id = _crear_insumo(cur, categoria_id, sucursal_id=992, nombre="Insumo RF-93")
        _registrar_insumo_suministrado(cur, proveedor_id, insumo_id, precio_vigente=10)
        orden_id = _crear_orden(cur, proveedor_id, sucursal_id=992)
        linea_id = _agregar_linea(cur, orden_id, insumo_id, cantidad=10)
        _transicion(cur, orden_id, "PENDIENTE_APROBACION")
        _transicion(cur, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
        _informar(cur, linea_id, "DISPONIBLE", precio=10)
        _agregar_fecha(cur, orden_id)
        _transicion(cur, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)
        recepcion_linea = _entregar_y_recibir(cur, orden_id, linea_id, entregado=10, recibido=10)
    setup.close()

    barrera = threading.Barrier(2)
    resultados = []

    def aprobar_todo():
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                barrera.wait()
                _verificar(cur, recepcion_linea, aprobada=10)
                time.sleep(0.5)
            conn.commit()
            resultados.append("OK")
        except psycopg2.Error as error:
            conn.rollback()
            resultados.append(type(error).__name__)
        finally:
            conn.close()

    hilos = [threading.Thread(target=aprobar_todo) for _ in range(2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["OK", "RaiseException"]
    verificar = psycopg2.connect(database_url)
    with verificar.cursor() as cur:
        cur.execute("SELECT count(*) FROM movimiento_inventario WHERE item_inventario_id = %s", (insumo_id,))
        assert cur.fetchone() == (1,)
        cur.execute("SELECT stock_actual FROM item_inventario WHERE id = %s", (insumo_id,))
        assert cur.fetchone() == (10,)
    verificar.close()
