import itertools
import threading
import time
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual
from test_proveedor import _crear_proveedor, _registrar_insumo_suministrado

JEFE_ALMACEN = 7


def _crear_orden(cursor, proveedor_id, sucursal_id=1, creado_por=JEFE_ALMACEN, **overrides):
    columnas = dict(proveedor_id=proveedor_id, sucursal_id=sucursal_id,
                    creado_por=creado_por, **overrides)
    campos = ", ".join(columnas.keys())
    placeholders = ", ".join(["%s"] * len(columnas))
    cursor.execute(
        f"INSERT INTO orden_compra ({campos}) VALUES ({placeholders}) RETURNING id",
        list(columnas.values()),
    )
    return cursor.fetchone()[0]


def _agregar_linea(cursor, orden_id, item_inventario_id, cantidad=10, precio_estimado=None):
    cursor.execute(
        """
        INSERT INTO orden_compra_linea (orden_compra_id, item_inventario_id, cantidad, precio_estimado)
        VALUES (%s, %s, %s, %s) RETURNING id
        """,
        (orden_id, item_inventario_id, cantidad, precio_estimado),
    )
    return cursor.fetchone()[0]


_nits = itertools.count(1)


def _proveedor_con_insumo(cursor, sucursal_id=1, precio_vigente=4200,
                          nombre_insumo="Leche entera", categoria_id=None):
    """Un proveedor activo que suministra un insumo activo de la sucursal.
    NIT y categoría salen únicos, para poder llamarlo varias veces en un test."""
    if categoria_id is None:
        categoria_id = _crear_categoria(cursor, nombre=f"Categoría de {nombre_insumo}")
    proveedor_id = _crear_proveedor(cursor, nit=f"900{next(_nits):06d}",
                                    nombre=f"Proveedor de {nombre_insumo}")
    insumo_id = _crear_insumo(cursor, categoria_id, sucursal_id=sucursal_id, nombre=nombre_insumo)
    _registrar_insumo_suministrado(cursor, proveedor_id, insumo_id, precio_vigente=precio_vigente)
    return proveedor_id, insumo_id


# --- la orden (RF-3, RF-9, RF-13) ---

def test_crear_orden_en_borrador_con_lineas(cursor):
    # RF-9 (un solo proveedor, insumos y cantidades) y RF-13 (borrador).
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    queso_id = _crear_insumo(cursor, _crear_categoria(cursor, nombre="Quesos"), nombre="Queso crema")
    _registrar_insumo_suministrado(cursor, proveedor_id, queso_id, precio_vigente=9800)

    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, leche_id, cantidad=20)
    _agregar_linea(cursor, orden_id, queso_id, cantidad=5.5)

    cursor.execute("SELECT estado, proveedor_id, creado_por FROM orden_compra WHERE id = %s", (orden_id,))
    assert cursor.fetchone() == ("BORRADOR", proveedor_id, JEFE_ALMACEN)
    cursor.execute(
        "SELECT item_inventario_id, cantidad FROM orden_compra_linea "
        "WHERE orden_compra_id = %s ORDER BY cantidad",
        (orden_id,),
    )
    assert cursor.fetchall() == [(queso_id, 5.5), (leche_id, 20)]


def test_rechaza_crear_una_orden_en_otro_estado_que_borrador(cursor):
    # Todas nacen en borrador; los demás estados solo llegan por transición.
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _crear_orden(cursor, proveedor_id, estado="APROBADA")


def test_rechaza_orden_de_un_proveedor_inactivo(cursor):
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    cursor.execute("UPDATE proveedor SET activo = false WHERE id = %s", (proveedor_id,))
    with pytest.raises(psycopg2.errors.RaiseException):
        _crear_orden(cursor, proveedor_id)


def test_rechaza_update_directo_del_estado(cursor):
    # Decisión #2 / ADR 0003: el estado cambia solo registrando una transición.
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute("UPDATE orden_compra SET estado = 'APROBADA' WHERE id = %s", (orden_id,))


def test_rechaza_borrar_una_orden(cursor):
    # Requisito no funcional de trazabilidad: nada se borra; una orden que
    # no sigue se cancela (transición a CANCELADA).
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute("DELETE FROM orden_compra WHERE id = %s", (orden_id,))


@pytest.mark.parametrize("columna, valor", [("proveedor_id", None), ("sucursal_id", 2)])
def test_rechaza_cambiar_proveedor_o_sucursal_de_la_orden(cursor, columna, valor):
    # Si se pudieran cambiar, las líneas ya cargadas dejarían de cumplir
    # RF-10 (insumos del proveedor) o RF-11 (una sola sucursal).
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, insumo_id)
    if valor is None:
        valor = _crear_proveedor(cursor, nit="800555444-1", nombre="Otro proveedor")
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(f"UPDATE orden_compra SET {columna} = %s WHERE id = %s", (valor, orden_id))


# --- las líneas (RF-10, RF-11, RF-76, RF-82, RF-83, RF-84) ---

def test_rechaza_un_insumo_que_el_proveedor_no_suministra(cursor):
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    ajeno_id = _crear_insumo(cursor, _crear_categoria(cursor, nombre="Cárnicos"), nombre="Carne molida")
    orden_id = _crear_orden(cursor, proveedor_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea(cursor, orden_id, ajeno_id)


def test_rechaza_un_insumo_de_otra_sucursal(cursor):
    categoria_id = _crear_categoria(cursor)
    proveedor_id, _ = _proveedor_con_insumo(cursor, sucursal_id=1, categoria_id=categoria_id)
    # El proveedor sí lo suministra, pero en la sucursal 2 (RF-11).
    leche_sucursal_2 = _crear_insumo(cursor, categoria_id, sucursal_id=2)
    _registrar_insumo_suministrado(cursor, proveedor_id, leche_sucursal_2)
    orden_id = _crear_orden(cursor, proveedor_id, sucursal_id=1)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea(cursor, orden_id, leche_sucursal_2)


def test_rechaza_el_mismo_insumo_dos_veces(cursor):
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, insumo_id, cantidad=10)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _agregar_linea(cursor, orden_id, insumo_id, cantidad=5)


@pytest.mark.parametrize("cantidad", [0, -1])
def test_rechaza_cantidad_cero_o_negativa(cursor, cantidad):
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _agregar_linea(cursor, orden_id, insumo_id, cantidad=cantidad)


def test_rechaza_un_insumo_inactivo(cursor):
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor)
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))
    orden_id = _crear_orden(cursor, proveedor_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea(cursor, orden_id, insumo_id)


def test_cambiar_el_insumo_de_una_linea_vuelve_a_validarlo(cursor):
    # Las reglas de RF-10/RF-11/RF-84 valen también si se cambia el insumo
    # de una línea ya cargada, no solo al agregarla.
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor)
    ajeno_id = _crear_insumo(cursor, _crear_categoria(cursor, nombre="Cárnicos"), nombre="Carne molida")
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_id = _agregar_linea(cursor, orden_id, insumo_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            "UPDATE orden_compra_linea SET item_inventario_id = %s WHERE id = %s", (ajeno_id, linea_id)
        )


def test_precio_estimado_toma_el_precio_vigente_si_no_se_indica(cursor):
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor, precio_vigente=4200)
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_id = _agregar_linea(cursor, orden_id, insumo_id)
    cursor.execute("SELECT precio_estimado FROM orden_compra_linea WHERE id = %s", (linea_id,))
    assert cursor.fetchone() == (4200,)


def test_precio_estimado_indicado_no_se_reemplaza(cursor):
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor, precio_vigente=4200)
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_id = _agregar_linea(cursor, orden_id, insumo_id, precio_estimado=3900)
    cursor.execute("SELECT precio_estimado FROM orden_compra_linea WHERE id = %s", (linea_id,))
    assert cursor.fetchone() == (3900,)


def test_sin_precio_vigente_ni_indicado_queda_sin_precio(cursor):
    # Se permite en borrador; exigir precio es regla del envío (RF-107, T4).
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor, precio_vigente=None)
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_id = _agregar_linea(cursor, orden_id, insumo_id)
    cursor.execute("SELECT precio_estimado FROM orden_compra_linea WHERE id = %s", (linea_id,))
    assert cursor.fetchone() == (None,)


# --- transiciones de estado (ADR 0003): T4 ---

ADMINISTRADOR = 2


def _transicion(cursor, orden_id, estado_nuevo, usuario_id=JEFE_ALMACEN, motivo=None):
    cursor.execute(
        """
        INSERT INTO orden_compra_transicion (orden_compra_id, estado_nuevo, usuario_id, motivo)
        VALUES (%s, %s, %s, %s) RETURNING id
        """,
        (orden_id, estado_nuevo, usuario_id, motivo),
    )
    return cursor.fetchone()[0]


def _estado(cursor, orden_id):
    cursor.execute("SELECT estado FROM orden_compra WHERE id = %s", (orden_id,))
    return cursor.fetchone()[0]


def _orden_en_borrador(cursor, **kwargs):
    """Orden con una línea de un insumo que el proveedor suministra."""
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor, **kwargs)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, insumo_id, cantidad=10)
    return orden_id


def _orden_pendiente_aprobacion(cursor, **kwargs):
    orden_id = _orden_en_borrador(cursor, **kwargs)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    return orden_id


def _orden_aprobada(cursor, **kwargs):
    orden_id = _orden_pendiente_aprobacion(cursor, **kwargs)
    _transicion(cursor, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
    return orden_id


def test_enviar_a_aprobacion_registra_usuario_y_fecha(cursor):
    # RF-108, y el historial que da el ADR 0003.
    orden_id = _orden_en_borrador(cursor)
    transicion_id = _transicion(cursor, orden_id, "PENDIENTE_APROBACION")

    assert _estado(cursor, orden_id) == "PENDIENTE_APROBACION"
    cursor.execute(
        """
        SELECT estado_anterior, estado_nuevo, usuario_id, creado_en IS NOT NULL
        FROM orden_compra_transicion WHERE id = %s
        """,
        (transicion_id,),
    )
    assert cursor.fetchone() == ("BORRADOR", "PENDIENTE_APROBACION", JEFE_ALMACEN, True)


def test_rechaza_enviar_una_orden_sin_insumos(cursor):
    # RF-106.
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "PENDIENTE_APROBACION")


def test_rechaza_enviar_una_orden_con_una_linea_sin_precio(cursor):
    # RF-107.
    orden_id = _orden_en_borrador(cursor, precio_vigente=None)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "PENDIENTE_APROBACION")


def test_rechaza_enviar_la_orden_de_un_proveedor_que_se_desactivo(cursor):
    # RF-3 también vale para un borrador creado antes de desactivarlo.
    orden_id = _orden_en_borrador(cursor)
    cursor.execute(
        "UPDATE proveedor SET activo = false "
        "WHERE id = (SELECT proveedor_id FROM orden_compra WHERE id = %s)",
        (orden_id,),
    )
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, "PENDIENTE_APROBACION")


def test_aprobar_registra_usuario_y_fecha(cursor):
    # RF-15.
    orden_id = _orden_pendiente_aprobacion(cursor)
    transicion_id = _transicion(cursor, orden_id, "APROBADA", usuario_id=ADMINISTRADOR)
    assert _estado(cursor, orden_id) == "APROBADA"
    cursor.execute(
        "SELECT usuario_id, creado_en IS NOT NULL FROM orden_compra_transicion WHERE id = %s",
        (transicion_id,),
    )
    assert cursor.fetchone() == (ADMINISTRADOR, True)


def test_rechazar_con_motivo_registra_usuario_y_fecha(cursor):
    # RF-16.
    orden_id = _orden_pendiente_aprobacion(cursor)
    transicion_id = _transicion(cursor, orden_id, "RECHAZADA", usuario_id=ADMINISTRADOR,
                                motivo="Precio muy alto")
    assert _estado(cursor, orden_id) == "RECHAZADA"
    cursor.execute(
        "SELECT usuario_id, motivo FROM orden_compra_transicion WHERE id = %s", (transicion_id,)
    )
    assert cursor.fetchone() == (ADMINISTRADOR, "Precio muy alto")


def test_rechaza_rechazar_sin_motivo(cursor):
    # RF-17.
    orden_id = _orden_pendiente_aprobacion(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _transicion(cursor, orden_id, "RECHAZADA", usuario_id=ADMINISTRADOR)


@pytest.mark.parametrize("decision", ["APROBADA", "RECHAZADA"])
def test_aprobar_o_rechazar_solo_desde_pendiente(cursor, decision):
    # RF-18: ni desde borrador (no se envió) ni desde aprobada (ya se decidió).
    en_borrador = _orden_en_borrador(cursor)
    aprobada = _orden_aprobada(cursor, nombre_insumo="Yogur")
    for orden_id in (en_borrador, aprobada):
        cursor.execute("SAVEPOINT intento")
        with pytest.raises(psycopg2.errors.RaiseException):
            _transicion(cursor, orden_id, decision, usuario_id=ADMINISTRADOR, motivo="x")
        cursor.execute("ROLLBACK TO SAVEPOINT intento")


@pytest.mark.parametrize("preparar", [_orden_en_borrador, _orden_pendiente_aprobacion, _orden_aprobada])
def test_cancelar_una_orden_abierta_con_motivo(cursor, preparar):
    # RF-19.
    orden_id = preparar(cursor)
    _transicion(cursor, orden_id, "CANCELADA", motivo="Ya no hace falta")
    assert _estado(cursor, orden_id) == "CANCELADA"


def test_rechaza_cancelar_sin_motivo(cursor):
    orden_id = _orden_en_borrador(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _transicion(cursor, orden_id, "CANCELADA")


@pytest.mark.parametrize("destino", ["APROBADA", "RECIBIDA", "BORRADOR"])
def test_rechaza_una_transicion_fuera_de_la_matriz(cursor, destino):
    orden_id = _orden_en_borrador(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _transicion(cursor, orden_id, destino, usuario_id=ADMINISTRADOR)


@pytest.mark.parametrize("final, motivo", [("RECHAZADA", "Precio muy alto"), ("CANCELADA", "Ya no hace falta")])
def test_rechaza_cualquier_transicion_desde_un_estado_final(cursor, final, motivo):
    # RF-110: un estado final no admite más cambios.
    orden_id = _orden_pendiente_aprobacion(cursor)
    _transicion(cursor, orden_id, final, usuario_id=ADMINISTRADOR, motivo=motivo)
    for destino in ("PENDIENTE_APROBACION", "APROBADA", "CANCELADA"):
        cursor.execute("SAVEPOINT intento")
        with pytest.raises(psycopg2.errors.RaiseException):
            _transicion(cursor, orden_id, destino, usuario_id=ADMINISTRADOR, motivo="otra vez")
        cursor.execute("ROLLBACK TO SAVEPOINT intento")


# --- líneas congeladas fuera de borrador (RF-81) ---

def test_en_borrador_las_lineas_se_editan_y_se_borran(cursor):
    orden_id = _orden_en_borrador(cursor)
    cursor.execute(
        "UPDATE orden_compra_linea SET cantidad = 15 WHERE orden_compra_id = %s", (orden_id,)
    )
    cursor.execute("DELETE FROM orden_compra_linea WHERE orden_compra_id = %s", (orden_id,))
    cursor.execute("SELECT count(*) FROM orden_compra_linea WHERE orden_compra_id = %s", (orden_id,))
    assert cursor.fetchone() == (0,)


@pytest.mark.parametrize("sentencia", [
    "UPDATE orden_compra_linea SET cantidad = 99 WHERE orden_compra_id = %s",
    "UPDATE orden_compra_linea SET precio_estimado = 1 WHERE orden_compra_id = %s",
    "DELETE FROM orden_compra_linea WHERE orden_compra_id = %s",
])
def test_rechaza_editar_lineas_fuera_de_borrador(cursor, sentencia):
    orden_id = _orden_pendiente_aprobacion(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (orden_id,))


def test_rechaza_agregar_lineas_fuera_de_borrador(cursor):
    categoria_id = _crear_categoria(cursor)
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor, categoria_id=categoria_id)
    otro_id = _crear_insumo(cursor, categoria_id, nombre="Yogur")
    _registrar_insumo_suministrado(cursor, proveedor_id, otro_id, precio_vigente=3000)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, insumo_id)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    with pytest.raises(psycopg2.errors.RaiseException):
        _agregar_linea(cursor, orden_id, otro_id)


def test_rechaza_mover_una_linea_a_otra_orden(cursor):
    # Mover una línea se saltearía las validaciones de la orden de destino.
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor)
    origen = _crear_orden(cursor, proveedor_id)
    destino = _crear_orden(cursor, proveedor_id)
    linea_id = _agregar_linea(cursor, origen, insumo_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            "UPDATE orden_compra_linea SET orden_compra_id = %s WHERE id = %s", (destino, linea_id)
        )


# --- el historial de transiciones es de solo agregar ---

@pytest.mark.parametrize("sentencia", [
    "UPDATE orden_compra_transicion SET motivo = 'alterado' WHERE orden_compra_id = %s",
    "DELETE FROM orden_compra_transicion WHERE orden_compra_id = %s",
])
def test_transiciones_no_se_editan_ni_se_borran(cursor, sentencia):
    orden_id = _orden_pendiente_aprobacion(cursor)
    with pytest.raises(psycopg2.errors.RaiseException) as error:
        cursor.execute(sentencia, (orden_id,))
    # El mensaje es de Compras, no el consejo de Inventario sobre ajustes.
    assert "AJUSTE" not in str(error.value)
    assert "transición" in str(error.value)


# --- concurrencia (RF-112) ---

def test_aprobar_y_rechazar_a_la_vez_solo_tiene_efecto_uno(esquema, database_url):
    # Aprobar y rechazar se excluyen: la que llega segunda tiene que ver el
    # estado que dejó la primera y fallar. (Cancelar una orden recién
    # aprobada, en cambio, es válido: por eso la prueba es con estas dos.)
    setup = psycopg2.connect(database_url)
    setup.autocommit = True
    with setup.cursor() as cur:
        categoria_id = _crear_categoria(cur, nombre="Concurrencia RF-112")
        proveedor_id = _crear_proveedor(cur, nit="112112112", nombre="Proveedor RF-112")
        insumo_id = _crear_insumo(cur, categoria_id, sucursal_id=996, nombre="Insumo RF-112")
        _registrar_insumo_suministrado(cur, proveedor_id, insumo_id, precio_vigente=1000)
        orden_id = _crear_orden(cur, proveedor_id, sucursal_id=996)
        _agregar_linea(cur, orden_id, insumo_id)
        _transicion(cur, orden_id, "PENDIENTE_APROBACION")
    setup.close()

    barrera = threading.Barrier(2)
    resultados = {}

    def decidir(estado, motivo):
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                barrera.wait()
                _transicion(cur, orden_id, estado, usuario_id=ADMINISTRADOR, motivo=motivo)
                time.sleep(0.5)  # la transacción sigue abierta mientras la otra intenta
            conn.commit()
            resultados[estado] = "OK"
        except psycopg2.Error:
            conn.rollback()
            resultados[estado] = "RECHAZADO"
        finally:
            conn.close()

    hilos = [threading.Thread(target=decidir, args=("APROBADA", None)),
             threading.Thread(target=decidir, args=("RECHAZADA", "Precio muy alto"))]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados.values()) == ["OK", "RECHAZADO"]
    ganadora = next(estado for estado, r in resultados.items() if r == "OK")
    verificar = psycopg2.connect(database_url)
    with verificar.cursor() as cur:
        assert _estado(cur, orden_id) == ganadora
        cur.execute(
            "SELECT estado_anterior, estado_nuevo FROM orden_compra_transicion "
            "WHERE orden_compra_id = %s AND estado_anterior = 'PENDIENTE_APROBACION'",
            (orden_id,),
        )
        assert cur.fetchall() == [("PENDIENTE_APROBACION", ganadora)]
    verificar.close()


# --- vista_orden_compra_resumen: valor estimado e historial (T5) ---

def _resumen(cursor, orden_id, columna):
    cursor.execute(f"SELECT {columna} FROM vista_orden_compra_resumen WHERE id = %s", (orden_id,))
    return cursor.fetchone()[0]


def test_valor_estimado_suma_cantidad_por_precio_de_cada_linea(cursor):
    # RF-12: 10 x 4200 + 5.5 x 9800 = 42000 + 53900.
    proveedor_id, leche_id = _proveedor_con_insumo(cursor, precio_vigente=4200)
    queso_id = _crear_insumo(cursor, _crear_categoria(cursor, nombre="Quesos"), nombre="Queso crema")
    _registrar_insumo_suministrado(cursor, proveedor_id, queso_id, precio_vigente=9800)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, leche_id, cantidad=10)
    _agregar_linea(cursor, orden_id, queso_id, cantidad=5.5)
    assert _resumen(cursor, orden_id, "valor_estimado") == 95900


def test_valor_estimado_se_redondea_a_centavos(cursor):
    # ADR 0001: los montos llevan 2 decimales. 0.333 x 1000.01 = 333.00333.
    proveedor_id, insumo_id = _proveedor_con_insumo(cursor, precio_vigente=1000.01)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, insumo_id, cantidad=0.333)
    cursor.execute(
        "SELECT valor_estimado, scale(valor_estimado) FROM vista_orden_compra_resumen WHERE id = %s",
        (orden_id,),
    )
    assert cursor.fetchone() == (333.00, 2)


def test_valor_estimado_de_una_orden_sin_lineas_es_cero(cursor):
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    orden_id = _crear_orden(cursor, proveedor_id)
    assert _resumen(cursor, orden_id, "valor_estimado") == 0


def test_valor_estimado_con_una_linea_sin_precio_queda_desconocido(cursor):
    # Una suma parcial parecería completa y subestimaría la orden.
    categoria_id = _crear_categoria(cursor)
    proveedor_id, con_precio = _proveedor_con_insumo(cursor, precio_vigente=4200, categoria_id=categoria_id)
    sin_precio = _crear_insumo(cursor, categoria_id, nombre="Yogur")
    _registrar_insumo_suministrado(cursor, proveedor_id, sin_precio)
    orden_id = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, orden_id, con_precio)
    _agregar_linea(cursor, orden_id, sin_precio)
    assert _resumen(cursor, orden_id, "valor_estimado") is None


def test_historial_filtra_por_proveedor(cursor):
    # RF-70.
    proveedor_a, _ = _proveedor_con_insumo(cursor, nombre_insumo="Leche entera")
    proveedor_b, _ = _proveedor_con_insumo(cursor, nombre_insumo="Carne molida")
    orden_a = _crear_orden(cursor, proveedor_a)
    _crear_orden(cursor, proveedor_b)
    cursor.execute("SELECT id FROM vista_orden_compra_resumen WHERE proveedor_id = %s", (proveedor_a,))
    assert [r[0] for r in cursor.fetchall()] == [orden_a]


def test_historial_filtra_por_rango_de_fechas_de_creacion(cursor):
    # RF-70: la fecha es la de creación de la orden.
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    vieja = _crear_orden(cursor, proveedor_id, creado_en=datetime.now(timezone.utc) - timedelta(days=40))
    reciente = _crear_orden(cursor, proveedor_id)
    cursor.execute(
        """
        SELECT id FROM vista_orden_compra_resumen
        WHERE proveedor_id = %s AND creado_en >= now() - interval '30 days'
        """,
        (proveedor_id,),
    )
    assert [r[0] for r in cursor.fetchall()] == [reciente]
    cursor.execute(
        """
        SELECT id FROM vista_orden_compra_resumen
        WHERE proveedor_id = %s AND creado_en < now() - interval '30 days'
        """,
        (proveedor_id,),
    )
    assert [r[0] for r in cursor.fetchall()] == [vieja]


def test_historial_filtra_por_estado(cursor):
    # RF-70.
    categoria_id = _crear_categoria(cursor)
    proveedor_id, leche_id = _proveedor_con_insumo(cursor, categoria_id=categoria_id)
    queso_id = _crear_insumo(cursor, categoria_id, nombre="Queso crema")
    _registrar_insumo_suministrado(cursor, proveedor_id, queso_id, precio_vigente=9800)
    en_borrador = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, en_borrador, leche_id)
    enviada = _crear_orden(cursor, proveedor_id)
    _agregar_linea(cursor, enviada, queso_id)
    _transicion(cursor, enviada, "PENDIENTE_APROBACION")

    cursor.execute(
        "SELECT id FROM vista_orden_compra_resumen WHERE proveedor_id = %s AND estado = %s",
        (proveedor_id, "PENDIENTE_APROBACION"),
    )
    assert [r[0] for r in cursor.fetchall()] == [enviada]


def test_historial_sin_coincidencias_devuelve_vacio(cursor):
    # RF-72.
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    _crear_orden(cursor, proveedor_id)
    cursor.execute(
        "SELECT id FROM vista_orden_compra_resumen WHERE proveedor_id = %s AND estado = 'RECIBIDA'",
        (proveedor_id,),
    )
    assert cursor.fetchall() == []


# --- solicitudes de reabastecimiento en Compras (T6) ---

USUARIO_PROVEEDOR = 15


def _crear_solicitud(cursor, item_inventario_id, cantidad_sugerida=5, estado="PENDIENTE"):
    cursor.execute(
        """
        INSERT INTO solicitud_reabastecimiento (item_inventario_id, cantidad_sugerida, estado)
        VALUES (%s, %s, %s) RETURNING id
        """,
        (item_inventario_id, cantidad_sugerida, estado),
    )
    return cursor.fetchone()[0]


def _registrar_consulta(cursor, solicitud_id, proveedor_id, usuario_id=USUARIO_PROVEEDOR):
    cursor.execute(
        """
        INSERT INTO solicitud_consulta_proveedor (solicitud_reabastecimiento_id, proveedor_id, usuario_id)
        VALUES (%s, %s, %s) RETURNING id
        """,
        (solicitud_id, proveedor_id, usuario_id),
    )
    return cursor.fetchone()[0]


def _vincular(cursor, solicitud_id, linea_id):
    cursor.execute(
        """
        INSERT INTO solicitud_orden_compra (solicitud_reabastecimiento_id, orden_compra_linea_id)
        VALUES (%s, %s) RETURNING id
        """,
        (solicitud_id, linea_id),
    )
    return cursor.fetchone()[0]


def _borrador_con_linea(cursor, proveedor_id, insumo_id):
    orden_id = _crear_orden(cursor, proveedor_id)
    return orden_id, _agregar_linea(cursor, orden_id, insumo_id)


def test_proveedor_ve_las_solicitudes_pendientes_de_sus_insumos(cursor):
    # RF-7: ni las de insumos que no suministra, ni las que ya no están pendientes.
    categoria_id = _crear_categoria(cursor)
    proveedor_id, leche_id = _proveedor_con_insumo(cursor, categoria_id=categoria_id)
    queso_id = _crear_insumo(cursor, categoria_id, nombre="Queso crema")
    _registrar_insumo_suministrado(cursor, proveedor_id, queso_id)
    carne_id = _crear_insumo(cursor, categoria_id, nombre="Carne molida")  # no la suministra

    pendiente = _crear_solicitud(cursor, leche_id)
    _crear_solicitud(cursor, queso_id, estado="ATENDIDA")
    _crear_solicitud(cursor, carne_id)

    cursor.execute(
        "SELECT solicitud_id FROM vista_solicitudes_por_proveedor WHERE proveedor_id = %s",
        (proveedor_id,),
    )
    assert [r[0] for r in cursor.fetchall()] == [pendiente]


def test_registrar_la_consulta_sin_cambiar_el_estado(cursor):
    # RF-8.
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    solicitud_id = _crear_solicitud(cursor, leche_id)
    consulta_id = _registrar_consulta(cursor, solicitud_id, proveedor_id)

    cursor.execute(
        "SELECT usuario_id, creado_en IS NOT NULL FROM solicitud_consulta_proveedor WHERE id = %s",
        (consulta_id,),
    )
    assert cursor.fetchone() == (USUARIO_PROVEEDOR, True)
    cursor.execute("SELECT estado FROM solicitud_reabastecimiento WHERE id = %s", (solicitud_id,))
    assert cursor.fetchone() == ("PENDIENTE",)
    cursor.execute(
        "SELECT consultada FROM vista_solicitudes_por_proveedor "
        "WHERE proveedor_id = %s AND solicitud_id = %s",
        (proveedor_id, solicitud_id),
    )
    assert cursor.fetchone() == (True,)


def test_la_consulta_se_registra_una_vez_por_proveedor(cursor):
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    solicitud_id = _crear_solicitud(cursor, leche_id)
    _registrar_consulta(cursor, solicitud_id, proveedor_id)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _registrar_consulta(cursor, solicitud_id, proveedor_id)


def test_rechaza_consultar_una_solicitud_de_un_insumo_que_no_suministra(cursor):
    # Coherente con RF-7: solo ve (y consulta) las de sus insumos.
    proveedor_id, _ = _proveedor_con_insumo(cursor)
    carne_id = _crear_insumo(cursor, _crear_categoria(cursor, nombre="Cárnicos"), nombre="Carne molida")
    solicitud_id = _crear_solicitud(cursor, carne_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _registrar_consulta(cursor, solicitud_id, proveedor_id)


@pytest.mark.parametrize("sentencia", [
    "UPDATE solicitud_consulta_proveedor SET usuario_id = 99 WHERE id = %s",
    "DELETE FROM solicitud_consulta_proveedor WHERE id = %s",
])
def test_las_consultas_no_se_editan_ni_se_borran(cursor, sentencia):
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    consulta_id = _registrar_consulta(cursor, _crear_solicitud(cursor, leche_id), proveedor_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (consulta_id,))


def test_vincular_solicitudes_a_las_lineas_de_sus_insumos(cursor):
    # RF-14: una orden puede atender varias solicitudes, una por insumo.
    categoria_id = _crear_categoria(cursor)
    proveedor_id, leche_id = _proveedor_con_insumo(cursor, categoria_id=categoria_id)
    queso_id = _crear_insumo(cursor, categoria_id, nombre="Queso crema")
    _registrar_insumo_suministrado(cursor, proveedor_id, queso_id, precio_vigente=9800)
    orden_id = _crear_orden(cursor, proveedor_id)
    linea_leche = _agregar_linea(cursor, orden_id, leche_id)
    linea_queso = _agregar_linea(cursor, orden_id, queso_id)

    _vincular(cursor, _crear_solicitud(cursor, leche_id), linea_leche)
    _vincular(cursor, _crear_solicitud(cursor, queso_id), linea_queso)

    cursor.execute(
        """
        SELECT count(*) FROM solicitud_orden_compra v
        JOIN orden_compra_linea l ON l.id = v.orden_compra_linea_id
        WHERE l.orden_compra_id = %s AND v.desvinculada_en IS NULL
        """,
        (orden_id,),
    )
    assert cursor.fetchone() == (2,)


def test_rechaza_vincular_a_la_linea_de_otro_insumo(cursor):
    # RF-80.
    categoria_id = _crear_categoria(cursor)
    proveedor_id, leche_id = _proveedor_con_insumo(cursor, categoria_id=categoria_id)
    queso_id = _crear_insumo(cursor, categoria_id, nombre="Queso crema")
    _, linea_leche = _borrador_con_linea(cursor, proveedor_id, leche_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _vincular(cursor, _crear_solicitud(cursor, queso_id), linea_leche)


@pytest.mark.parametrize("estado", ["ATENDIDA", "CANCELADA", "ENVIADA"])
def test_rechaza_vincular_una_solicitud_que_no_esta_pendiente(cursor, estado):
    # RF-109.
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    _, linea_id = _borrador_con_linea(cursor, proveedor_id, leche_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        _vincular(cursor, _crear_solicitud(cursor, leche_id, estado=estado), linea_id)


def test_rechaza_vincular_a_una_orden_que_ya_no_esta_en_borrador(cursor):
    # RF-14: se vincula al generar la orden; enviada, su contenido se congela (RF-81).
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    orden_id, linea_id = _borrador_con_linea(cursor, proveedor_id, leche_id)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    with pytest.raises(psycopg2.errors.RaiseException):
        _vincular(cursor, _crear_solicitud(cursor, leche_id), linea_id)


def test_rechaza_vincular_una_solicitud_ya_vinculada_a_otra_orden_abierta(cursor):
    # RF-79.
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    solicitud_id = _crear_solicitud(cursor, leche_id)
    _, linea_1 = _borrador_con_linea(cursor, proveedor_id, leche_id)
    _, linea_2 = _borrador_con_linea(cursor, proveedor_id, leche_id)
    _vincular(cursor, solicitud_id, linea_1)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _vincular(cursor, solicitud_id, linea_2)


@pytest.mark.parametrize("final", ["CANCELADA", "RECHAZADA"])
def test_cancelar_o_rechazar_desvincula_y_la_solicitud_se_puede_volver_a_vincular(cursor, final):
    # RF-78: la solicitud sigue pendiente y puede atenderla otra orden.
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    solicitud_id = _crear_solicitud(cursor, leche_id)
    orden_id, linea_id = _borrador_con_linea(cursor, proveedor_id, leche_id)
    vinculo_id = _vincular(cursor, solicitud_id, linea_id)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    _transicion(cursor, orden_id, final, usuario_id=ADMINISTRADOR, motivo="No va")

    cursor.execute("SELECT desvinculada_en IS NOT NULL FROM solicitud_orden_compra WHERE id = %s", (vinculo_id,))
    assert cursor.fetchone() == (True,)
    cursor.execute("SELECT estado FROM solicitud_reabastecimiento WHERE id = %s", (solicitud_id,))
    assert cursor.fetchone() == ("PENDIENTE",)
    _, otra_linea = _borrador_con_linea(cursor, proveedor_id, leche_id)
    _vincular(cursor, solicitud_id, otra_linea)


def test_borrar_una_linea_en_borrador_borra_su_vinculo(cursor):
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    solicitud_id = _crear_solicitud(cursor, leche_id)
    _, linea_id = _borrador_con_linea(cursor, proveedor_id, leche_id)
    _vincular(cursor, solicitud_id, linea_id)
    cursor.execute("DELETE FROM orden_compra_linea WHERE id = %s", (linea_id,))
    cursor.execute(
        "SELECT count(*) FROM solicitud_orden_compra WHERE solicitud_reabastecimiento_id = %s",
        (solicitud_id,),
    )
    assert cursor.fetchone() == (0,)


@pytest.mark.parametrize("sentencia", [
    "DELETE FROM solicitud_orden_compra WHERE id = %s",
    "UPDATE solicitud_orden_compra SET vinculada_en = now() - interval '1 day' WHERE id = %s",
])
def test_fuera_de_borrador_un_vinculo_no_se_edita_ni_se_borra(cursor, sentencia):
    proveedor_id, leche_id = _proveedor_con_insumo(cursor)
    orden_id, linea_id = _borrador_con_linea(cursor, proveedor_id, leche_id)
    vinculo_id = _vincular(cursor, _crear_solicitud(cursor, leche_id), linea_id)
    _transicion(cursor, orden_id, "PENDIENTE_APROBACION")
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(sentencia, (vinculo_id,))


def test_dos_ordenes_vinculando_la_misma_solicitud_a_la_vez(esquema, database_url):
    # RF-79 ante concurrencia: el índice único parcial deja pasar una sola.
    setup = psycopg2.connect(database_url)
    setup.autocommit = True
    with setup.cursor() as cur:
        categoria_id = _crear_categoria(cur, nombre="Concurrencia RF-79")
        proveedor_id = _crear_proveedor(cur, nit="797979797", nombre="Proveedor RF-79")
        insumo_id = _crear_insumo(cur, categoria_id, sucursal_id=995, nombre="Insumo RF-79")
        _registrar_insumo_suministrado(cur, proveedor_id, insumo_id, precio_vigente=1000)
        solicitud_id = _crear_solicitud(cur, insumo_id)
        lineas = []
        for _ in range(2):
            orden_id = _crear_orden(cur, proveedor_id, sucursal_id=995)
            lineas.append(_agregar_linea(cur, orden_id, insumo_id))
    setup.close()

    barrera = threading.Barrier(2)
    resultados = []

    def vincular(linea_id):
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                barrera.wait()
                _vincular(cur, solicitud_id, linea_id)
                time.sleep(0.5)
            conn.commit()
            resultados.append("OK")
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            resultados.append("RECHAZADO")
        finally:
            conn.close()

    hilos = [threading.Thread(target=vincular, args=(linea,)) for linea in lineas]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados) == ["OK", "RECHAZADO"]
