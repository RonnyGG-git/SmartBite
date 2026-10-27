import threading
import time

import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo, _set_usuario_actual


def test_genera_codigo_con_prefijo_de_categoria(cursor):
    categoria_id = _crear_categoria(cursor, nombre="Lácteos")
    insumo_id = _crear_insumo(cursor, categoria_id, sucursal_id=1)
    cursor.execute("SELECT codigo_unico FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone()[0] == "LAC-00001"


def test_codigos_consecutivos_misma_categoria_y_sucursal(cursor):
    categoria_id = _crear_categoria(cursor, nombre="Lácteos")
    id1 = _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche")
    id2 = _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Yogur")
    cursor.execute(
        "SELECT id, codigo_unico FROM item_inventario WHERE id IN (%s, %s) ORDER BY id",
        (id1, id2),
    )
    codigos = [c for _, c in cursor.fetchall()]
    assert codigos == ["LAC-00001", "LAC-00002"]


def test_dos_sucursales_no_chocan_con_el_mismo_prefijo(cursor):
    # Antes de la corrección del plan, el UNIQUE era global y esto fallaba.
    categoria_id = _crear_categoria(cursor, nombre="Lácteos")
    id_sucursal_1 = _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche")
    id_sucursal_2 = _crear_insumo(cursor, categoria_id, sucursal_id=2, nombre="Leche")
    cursor.execute(
        "SELECT sucursal_id, codigo_unico FROM item_inventario WHERE id IN (%s, %s)",
        (id_sucursal_1, id_sucursal_2),
    )
    codigos = dict(cursor.fetchall())
    assert codigos == {1: "LAC-00001", 2: "LAC-00001"}


def test_rechaza_modificar_codigo_unico(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            "UPDATE item_inventario SET codigo_unico = 'OTRO-00001' WHERE id = %s",
            (insumo_id,),
        )


def test_permite_actualizar_otros_campos_sin_tocar_el_codigo(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    cursor.execute("SELECT codigo_unico FROM item_inventario WHERE id = %s", (insumo_id,))
    codigo_original = cursor.fetchone()[0]

    _set_usuario_actual(cursor, 1)
    cursor.execute(
        "UPDATE item_inventario SET descripcion = %s WHERE id = %s",
        ("Actualizado", insumo_id),
    )
    cursor.execute("SELECT codigo_unico FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone()[0] == codigo_original


# --- Verificación posterior (2026-09-23) ---

def test_prefijo_usa_solo_letras_de_la_categoria(cursor):
    # ADR 0002: "3 letras mayúsculas". Con un guion dentro de las 3 primeras
    # posiciones, el segundo insumo fallaba al leer el secuencial del primero.
    categoria_id = _crear_categoria(cursor, nombre="Té-hierbas")
    id1 = _crear_insumo(cursor, categoria_id, nombre="Manzanilla")
    id2 = _crear_insumo(cursor, categoria_id, nombre="Menta")
    cursor.execute(
        "SELECT codigo_unico FROM item_inventario WHERE id IN (%s, %s) ORDER BY id", (id1, id2)
    )
    assert [r[0] for r in cursor.fetchall()] == ["TEH-00001", "TEH-00002"]


def test_dos_altas_concurrentes_misma_categoria_y_sucursal(esquema, database_url):
    # Con MAX()+1 sin bloqueo, las dos transacciones calculaban el mismo
    # secuencial y la segunda moría por UniqueViolation.
    setup_conn = psycopg2.connect(database_url)
    setup_conn.autocommit = True
    with setup_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO categoria_insumo (nombre) VALUES ('Concurrencia código') RETURNING id"
        )
        categoria_id = cur.fetchone()[0]
    setup_conn.close()

    barrera = threading.Barrier(2)
    resultados = {}

    def alta(nombre):
        conn = psycopg2.connect(database_url)
        try:
            with conn.cursor() as cur:
                barrera.wait()
                cur.execute(
                    """
                    INSERT INTO item_inventario (nombre, unidad_medida, categoria_id, sucursal_id)
                    VALUES (%s, 'kg', %s, 997) RETURNING codigo_unico
                    """,
                    (nombre, categoria_id),
                )
                resultados[nombre] = cur.fetchone()[0]
                time.sleep(0.5)  # la transacción sigue abierta mientras la otra intenta
            conn.commit()
        except psycopg2.Error as error:
            conn.rollback()
            resultados[nombre] = type(error).__name__
        finally:
            conn.close()

    hilos = [threading.Thread(target=alta, args=(f"Insumo concurrente {n}",)) for n in (1, 2)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert sorted(resultados.values()) == ["CON-00001", "CON-00002"]
