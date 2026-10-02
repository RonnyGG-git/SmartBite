import itertools
import threading
import time

import psycopg2
import pytest

from test_confirmacion_orden import _agregar_fecha, _informar, _orden_confirmada
from test_entrega_recepcion import (
    _agregar_linea_entregada, _agregar_linea_recibida, _anular_entrega, _entrega_con_lineas,
    _orden_aceptada_en_parte, _recibir, _registrar_entrega,
)
from test_item_inventario import _crear_categoria, _crear_insumo
from test_orden_compra import (
    ADMINISTRADOR, JEFE_ALMACEN, USUARIO_PROVEEDOR, _agregar_linea, _borrador_con_linea,
    _crear_orden, _crear_solicitud, _estado, _proveedor_con_insumo, _transicion, _vincular,
)
from test_proveedor import _crear_proveedor, _registrar_insumo_suministrado
from test_verificacion_calidad import _entregar_y_recibir, _insumo_de, _stock, _verificar

OTRO_JEFE = 8
MOTIVO_FALTANTES = "El proveedor no va a entregar lo que falta"

_solicitudes = itertools.count(1)


def _saldo(cursor, linea_orden_id):
    cursor.execute(
        """
        SELECT cantidad_confirmada, recibida, aprobada, rechazada, cuarentena_vigente,
               sin_verificar, pendiente
        FROM vista_orden_compra_linea_saldo WHERE orden_compra_linea_id = %s
        """,
        (linea_orden_id,),
    )
    return cursor.fetchone()


def _cerrar_con_faltantes(cursor, orden_id, motivo=MOTIVO_FALTANTES, usuario_id=JEFE_ALMACEN):
    return _transicion(cursor, orden_id, "CERRADA_FALTANTES", usuario_id=usuario_id, motivo=motivo)


def _estado_solicitud(cursor, solicitud_id):
    cursor.execute("SELECT estado FROM solicitud_reabastecimiento WHERE id = %s", (solicitud_id,))
    return cursor.fetchone()[0]


def _orden_confirmada_con_solicitud(cursor):
    """Orden confirmada de 10 unidades de un insumo, vinculada a la solicitud
    de reabastecimiento de ese insumo. Devuelve (orden, línea, solicitud)."""
    proveedor_id, insumo_id = _proveedor_con_insumo(
        cursor, nombre_insumo=f"Harina de trigo {next(_solicitudes)}")
    solicitud_id = _crear_solicitud(cursor, insumo_id)
    orden_id, linea_id = _borrador_con_linea(cursor, proveedor_id, insumo_id)
    _vincular(cursor, solicitud_id, linea_id)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    _transicion(cursor, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
    _informar(cursor, linea_id, "DISPONIBLE", precio=3000)
    _agregar_fecha(cursor, orden_id)
    _transicion(cursor, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)
    return orden_id, linea_id, solicitud_id


def _orden_recibida(cursor):
    """Orden aceptada en parte (10 de leche; el queso no disponible). Llegan
    12 de leche, se aprueban 10 y la orden queda RECIBIDA con 2 recibidas sin
    clasificar y una segunda entrega registrada que nunca se recibió.
    Devuelve (orden, línea recibida, entrega sin recibir, línea de leche)."""
    orden_id, leche, _ = _orden_aceptada_en_parte(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=12, recibido=12)
    entrega_sin_recibir = _registrar_entrega(cursor, orden_id, [(leche, 1)])
    _verificar(cursor, recepcion_linea, aprobada=10)
    assert _estado(cursor, orden_id) == "RECIBIDA"
    return orden_id, recepcion_linea, entrega_sin_recibir, leche


def _orden_cerrada_con_faltantes(cursor):
    """Orden confirmada (10 de leche, 4 de queso) con una entrega de las dos
    cosas. Se confirma la recepción pero solo se carga la leche (6), se
    aprueba y se cierra con faltantes. Devuelve (orden, recepción, línea
    entregada del queso)."""
    orden_id, leche, queso = _orden_confirmada(cursor)
    entrega_id, (el_leche, el_queso) = _entrega_con_lineas(cursor, orden_id, [(leche, 6), (queso, 4)])
    recepcion_id = _recibir(cursor, entrega_id)
    recepcion_linea = _agregar_linea_recibida(cursor, recepcion_id, el_leche, 6)
    _verificar(cursor, recepcion_linea, aprobada=6)
    _cerrar_con_faltantes(cursor, orden_id)
    return orden_id, recepcion_id, el_queso


# --- lo pendiente de cada insumo (vista_orden_compra_linea_saldo) ---

def test_la_vista_de_saldos_muestra_lo_pendiente_de_cada_insumo(cursor):
    # Pendiente = confirmado − aprobado. Lo que está en cuarentena no cuenta
    # como aprobado hasta que se resuelve (RF-44).
    orden_id, leche, queso = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=8, recibido=8)
    _verificar(cursor, recepcion_linea, aprobada=5, rechazada=1, cuarentena=2)

    # confirmada, recibida, aprobada, rechazada, cuarentena, sin verificar, pendiente
    assert _saldo(cursor, leche) == (10, 8, 5, 1, 2, 0, 5)
    assert _saldo(cursor, queso) == (4, 0, 0, 0, 0, 0, 4)

    _verificar(cursor, recepcion_linea, aprobada=1, rechazada=1, desde_cuarentena=True)
    assert _saldo(cursor, leche) == (10, 8, 6, 2, 0, 0, 4)


def test_la_vista_muestra_lo_recibido_que_falta_verificar(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=8, recibido=7)
    _verificar(cursor, recepcion_linea, aprobada=3)
    assert _saldo(cursor, leche) == (10, 7, 3, 0, 0, 4, 7)


def test_un_insumo_no_disponible_no_queda_pendiente(cursor):
    # Cantidad confirmada = 0 si el proveedor lo informó no disponible.
    _, leche, queso = _orden_aceptada_en_parte(cursor)
    assert _saldo(cursor, leche) == (10, 0, 0, 0, 0, 0, 10)
    assert _saldo(cursor, queso) == (0, 0, 0, 0, 0, 0, 0)


# --- paso automático a RECIBIDA (RF-45, RF-46) ---

def test_la_orden_sigue_en_recepcion_mientras_queda_pendiente(cursor):
    # RF-46: la leche está completa, falta el queso.
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=10, recibido=10)
    _verificar(cursor, recepcion_linea, aprobada=10)
    assert _estado(cursor, orden_id) == "EN_RECEPCION"


def test_la_orden_pasa_sola_a_recibida_al_aprobarse_lo_ultimo(cursor):
    # RF-45, con el usuario de la verificación que la completó (ADR 0003).
    orden_id, leche, queso = _orden_confirmada(cursor)
    entrega_id, (el_leche, el_queso) = _entrega_con_lineas(cursor, orden_id, [(leche, 10), (queso, 4)])
    recepcion_id = _recibir(cursor, entrega_id)
    rl_leche = _agregar_linea_recibida(cursor, recepcion_id, el_leche, 10)
    rl_queso = _agregar_linea_recibida(cursor, recepcion_id, el_queso, 4)
    _verificar(cursor, rl_leche, aprobada=10)
    _verificar(cursor, rl_queso, aprobada=4, usuario_id=OTRO_JEFE)

    assert _estado(cursor, orden_id) == "RECIBIDA"
    cursor.execute(
        """
        SELECT estado_anterior, usuario_id, motivo FROM orden_compra_transicion
        WHERE orden_compra_id = %s AND estado_nuevo = 'RECIBIDA'
        """,
        (orden_id,),
    )
    assert cursor.fetchall() == [("EN_RECEPCION", OTRO_JEFE, None)]


def test_una_orden_aceptada_en_parte_queda_recibida_con_lo_disponible(cursor):
    # El queso no disponible tiene 0 confirmado: no deja la orden abierta.
    orden_id, leche, _ = _orden_aceptada_en_parte(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=10, recibido=10)
    _verificar(cursor, recepcion_linea, aprobada=10)
    assert _estado(cursor, orden_id) == "RECIBIDA"


def test_varias_entregas_y_una_cuarentena_completan_la_orden(cursor):
    orden_id, leche, _ = _orden_aceptada_en_parte(cursor)
    primera = _entregar_y_recibir(cursor, orden_id, leche, entregado=10, recibido=10)
    _verificar(cursor, primera, aprobada=7, cuarentena=3)
    assert _estado(cursor, orden_id) == "EN_RECEPCION"

    # De la cuarentena se aprueban 2 y se rechaza 1: falta 1.
    _verificar(cursor, primera, aprobada=2, rechazada=1, desde_cuarentena=True)
    assert _estado(cursor, orden_id) == "EN_RECEPCION"

    segunda = _entregar_y_recibir(cursor, orden_id, leche, entregado=1, recibido=1)
    _verificar(cursor, segunda, aprobada=1)
    assert _estado(cursor, orden_id) == "RECIBIDA"
    assert _stock(cursor, _insumo_de(cursor, leche)) == 10


def test_rechazar_o_poner_en_cuarentena_no_completa_la_orden(cursor):
    orden_id, leche, _ = _orden_aceptada_en_parte(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=10, recibido=10)
    _verificar(cursor, recepcion_linea, rechazada=4, cuarentena=6)
    assert _estado(cursor, orden_id) == "EN_RECEPCION"


def test_rechaza_marcar_recibida_a_mano_con_cantidad_pendiente(cursor):
    orden_id, leche, _ = _orden_aceptada_en_parte(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=10, recibido=10)
    _verificar(cursor, recepcion_linea, aprobada=6)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "RECIBIDA")


# --- solicitudes atendidas (RF-77) ---

def test_la_solicitud_vinculada_queda_atendida_al_recibir_la_orden(cursor):
    orden_id, linea_id, solicitud_id = _orden_confirmada_con_solicitud(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, linea_id, entregado=10, recibido=10)
    _verificar(cursor, recepcion_linea, aprobada=6)
    assert _estado_solicitud(cursor, solicitud_id) == "PENDIENTE"

    _verificar(cursor, recepcion_linea, aprobada=4)
    assert _estado(cursor, orden_id) == "RECIBIDA"
    assert _estado_solicitud(cursor, solicitud_id) == "ATENDIDA"


def test_la_solicitud_vinculada_queda_atendida_al_cerrar_con_faltantes(cursor):
    orden_id, linea_id, solicitud_id = _orden_confirmada_con_solicitud(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, linea_id, entregado=6, recibido=6)
    _verificar(cursor, recepcion_linea, aprobada=6)
    _cerrar_con_faltantes(cursor, orden_id)
    assert _estado_solicitud(cursor, solicitud_id) == "ATENDIDA"


def test_cerrar_la_orden_no_toca_solicitudes_de_otras_ordenes(cursor):
    orden_id, linea_id, _ = _orden_confirmada_con_solicitud(cursor)
    _, _, otra_solicitud = _orden_confirmada_con_solicitud(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, linea_id, entregado=10, recibido=10)
    _verificar(cursor, recepcion_linea, aprobada=10)
    assert _estado_solicitud(cursor, otra_solicitud) == "PENDIENTE"


# --- cerrar con faltantes (RF-94, RF-116) ---

def test_cerrar_con_faltantes_con_motivo(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=6, recibido=6)
    _verificar(cursor, recepcion_linea, aprobada=6)
    _cerrar_con_faltantes(cursor, orden_id)

    assert _estado(cursor, orden_id) == "CERRADA_FALTANTES"
    cursor.execute(
        """
        SELECT estado_anterior, usuario_id, motivo FROM orden_compra_transicion
        WHERE orden_compra_id = %s AND estado_nuevo = 'CERRADA_FALTANTES'
        """,
        (orden_id,),
    )
    assert cursor.fetchone() == ("EN_RECEPCION", JEFE_ALMACEN, MOTIVO_FALTANTES)
    assert _stock(cursor, _insumo_de(cursor, leche)) == 6  # lo aprobado no se toca


def test_cerrar_con_faltantes_exige_motivo(cursor):
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=6, recibido=6)
    _verificar(cursor, recepcion_linea, aprobada=6)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _cerrar_con_faltantes(cursor, orden_id, motivo=None)


def test_solo_se_cierra_con_faltantes_una_orden_en_recepcion(cursor):
    # RF-94. Sin nada entregado, lo que corresponde es cancelarla.
    orden_id, _, _ = _orden_confirmada(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _cerrar_con_faltantes(cursor, orden_id)


def test_rechaza_cerrar_con_una_entrega_sin_recibir(cursor):
    # RF-116. Anulada la entrega, sí se puede.
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=6, recibido=6)
    _verificar(cursor, recepcion_linea, aprobada=6)
    entrega_id = _registrar_entrega(cursor, orden_id, [(leche, 2)])

    cursor.execute("SAVEPOINT intento")
    with pytest.raises(psycopg2.errors.RaiseException):
        _cerrar_con_faltantes(cursor, orden_id)
    cursor.execute("ROLLBACK TO SAVEPOINT intento")

    _anular_entrega(cursor, entrega_id)
    _cerrar_con_faltantes(cursor, orden_id)
    assert _estado(cursor, orden_id) == "CERRADA_FALTANTES"


def test_rechaza_cerrar_con_cuarentena_vigente(cursor):
    # RF-116. Resuelta la cuarentena, sí se puede.
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=6, recibido=6)
    _verificar(cursor, recepcion_linea, aprobada=4, cuarentena=2)

    cursor.execute("SAVEPOINT intento")
    with pytest.raises(psycopg2.errors.RaiseException):
        _cerrar_con_faltantes(cursor, orden_id)
    cursor.execute("ROLLBACK TO SAVEPOINT intento")

    _verificar(cursor, recepcion_linea, rechazada=2, desde_cuarentena=True)
    _cerrar_con_faltantes(cursor, orden_id)
    assert _estado(cursor, orden_id) == "CERRADA_FALTANTES"


def test_rechaza_cerrar_con_lo_recibido_sin_verificar(cursor):
    # Precisión del RF-116: lo que llegó y no pasó por calidad quedaría fuera
    # del stock para siempre (después del cierre no se verifica, RF-110).
    orden_id, leche, _ = _orden_confirmada(cursor)
    recepcion_linea = _entregar_y_recibir(cursor, orden_id, leche, entregado=6, recibido=6)
    _verificar(cursor, recepcion_linea, aprobada=4)

    cursor.execute("SAVEPOINT intento")
    with pytest.raises(psycopg2.errors.RaiseException):
        _cerrar_con_faltantes(cursor, orden_id)
    cursor.execute("ROLLBACK TO SAVEPOINT intento")

    _verificar(cursor, recepcion_linea, rechazada=2)
    _cerrar_con_faltantes(cursor, orden_id)
    assert _estado(cursor, orden_id) == "CERRADA_FALTANTES"


# --- después del cierre no entra nada más (RF-110) ---

@pytest.mark.parametrize("cerrar", [_orden_recibida, _orden_cerrada_con_faltantes],
                         ids=["RECIBIDA", "CERRADA_FALTANTES"])
def test_rechaza_una_entrega_nueva_despues_del_cierre(cursor, cerrar):
    orden_id = cerrar(cursor)[0]
    with pytest.raises(psycopg2.errors.RaiseException):
        _registrar_entrega(cursor, orden_id)


def test_rechaza_agregar_insumos_a_una_entrega_despues_del_cierre(cursor):
    # La entrega que quedó sin recibir ya tiene la leche: sin la regla, el
    # rechazo sería el UniqueViolation de la línea repetida, no este.
    _, _, entrega_sin_recibir, leche = _orden_recibida(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea_entregada(cursor, entrega_sin_recibir, leche, 1)


def test_rechaza_recibir_una_entrega_despues_del_cierre(cursor):
    _, _, entrega_sin_recibir, _ = _orden_recibida(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _recibir(cursor, entrega_sin_recibir)


def test_rechaza_cargar_lo_recibido_despues_del_cierre(cursor):
    _, recepcion_id, el_queso = _orden_cerrada_con_faltantes(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea_recibida(cursor, recepcion_id, el_queso, 4)


def test_rechaza_verificar_despues_del_cierre(cursor):
    # Quedaron 2 recibidas de más sin clasificar: el exceso va como
    # discrepancia (RF-114), ya no como verificación.
    _, recepcion_linea, _, _ = _orden_recibida(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _verificar(cursor, recepcion_linea, rechazada=2)


@pytest.mark.parametrize("cerrar, destino", [
    (_orden_recibida, "CANCELADA"),
    (_orden_recibida, "CERRADA_FALTANTES"),
    (_orden_cerrada_con_faltantes, "CANCELADA"),
    (_orden_cerrada_con_faltantes, "EN_RECEPCION"),
], ids=["RECIBIDA-CANCELADA", "RECIBIDA-CERRADA_FALTANTES",
        "CERRADA_FALTANTES-CANCELADA", "CERRADA_FALTANTES-EN_RECEPCION"])
def test_un_estado_final_no_tiene_salida(cursor, cerrar, destino):
    orden_id = cerrar(cursor)[0]
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, destino, motivo="Intento después del cierre")


# --- concurrencia: cerrar con faltantes mientras llega una entrega (RF-116) ---

def test_cerrar_con_faltantes_mientras_se_registra_una_entrega(esquema, database_url):
    # La entrega empieza primero y tarda en confirmarse: el cierre tiene que
    # esperarla y verla (RF-116), no validar contra la orden de antes.
    setup = psycopg2.connect(database_url)
    setup.autocommit = True
    with setup.cursor() as cur:
        categoria_id = _crear_categoria(cur, nombre="Concurrencia RF-116")
        proveedor_id = _crear_proveedor(cur, nit="919191919", nombre="Proveedor RF-116")
        insumo_id = _crear_insumo(cur, categoria_id, sucursal_id=991, nombre="Insumo RF-116")
        _registrar_insumo_suministrado(cur, proveedor_id, insumo_id, precio_vigente=10)
        orden_id = _crear_orden(cur, proveedor_id, sucursal_id=991)
        linea_id = _agregar_linea(cur, orden_id, insumo_id, cantidad=10)
        _transicion(cur, orden_id, "PENDIENTE_APROBACION")
        _transicion(cur, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
        _informar(cur, linea_id, "DISPONIBLE", precio=10)
        _agregar_fecha(cur, orden_id)
        _transicion(cur, orden_id, "CONFIRMADA", usuario_id=USUARIO_PROVEEDOR)
        recepcion_linea = _entregar_y_recibir(cur, orden_id, linea_id, entregado=6, recibido=6)
        _verificar(cur, recepcion_linea, aprobada=6)
    setup.close()

    barrera = threading.Barrier(2)
    resultados = {}

    def ejecutar(nombre, accion, espera_antes, espera_despues):
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                barrera.wait()
                time.sleep(espera_antes)
                accion(cur)
                time.sleep(espera_despues)
            conn.commit()
            resultados[nombre] = "OK"
        except psycopg2.Error as error:
            conn.rollback()
            resultados[nombre] = type(error).__name__
        finally:
            conn.close()

    def entregar(cur):
        entrega_id = _registrar_entrega(cur, orden_id)
        _agregar_linea_entregada(cur, entrega_id, linea_id, 4)

    hilos = [
        threading.Thread(target=ejecutar, args=("entregar", entregar, 0, 1.0)),
        threading.Thread(target=ejecutar,
                         args=("cerrar", lambda cur: _cerrar_con_faltantes(cur, orden_id), 0.5, 0)),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert resultados == {"entregar": "OK", "cerrar": "RaiseException"}
    verificar = psycopg2.connect(database_url)
    with verificar.cursor() as cur:
        cur.execute("SELECT estado FROM orden_compra WHERE id = %s", (orden_id,))
        assert cur.fetchone() == ("EN_RECEPCION",)
    verificar.close()
