import psycopg2
import pytest

from test_item_inventario import _crear_categoria, _crear_insumo


def _crear_proveedor(cursor, nit="900123456-7", nombre="Lácteos del Norte", **overrides):
    columnas = dict(nit=nit, nombre=nombre, **overrides)
    campos = ", ".join(columnas.keys())
    placeholders = ", ".join(["%s"] * len(columnas))
    cursor.execute(
        f"INSERT INTO proveedor ({campos}) VALUES ({placeholders}) RETURNING id",
        list(columnas.values()),
    )
    return cursor.fetchone()[0]


def _registrar_insumo_suministrado(cursor, proveedor_id, item_inventario_id, precio_vigente=None):
    cursor.execute(
        """
        INSERT INTO proveedor_insumo (proveedor_id, item_inventario_id, precio_vigente)
        VALUES (%s, %s, %s) RETURNING id
        """,
        (proveedor_id, item_inventario_id, precio_vigente),
    )
    return cursor.fetchone()[0]


# --- proveedor (RF-1, RF-2, RF-74) ---

def test_crear_proveedor_con_nit_y_datos_de_contacto(cursor):
    proveedor_id = _crear_proveedor(
        cursor, contacto="Marta Ríos", telefono="3001234567",
        email="ventas@lacteosdelnorte.co", direccion="Cra 10 # 20-30",
    )
    cursor.execute(
        "SELECT nit, nombre, contacto, activo FROM proveedor WHERE id = %s", (proveedor_id,)
    )
    assert cursor.fetchone() == ("900123456-7", "Lácteos del Norte", "Marta Ríos", True)


@pytest.mark.parametrize("nit_repetido", ["9001234567", "900.123.456-7", " 900 123 456 7 "])
def test_rechaza_el_mismo_nit_con_otro_formato(cursor, nit_repetido):
    # RF-74: puntos, guiones y espacios no hacen distinto a un NIT.
    _crear_proveedor(cursor, nit="900123456-7")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _crear_proveedor(cursor, nit=nit_repetido, nombre="Otro nombre")


@pytest.mark.parametrize("nit_vacio", ["", "   ", "---", ". -"])
def test_rechaza_un_nit_sin_digitos_ni_letras(cursor, nit_vacio):
    # RF-1 exige el NIT: un texto que queda vacío al normalizarlo no
    # identifica a ningún proveedor.
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_proveedor(cursor, nit=nit_vacio)


def test_desactivar_proveedor_conserva_la_fila_y_lo_que_suministra(cursor):
    # RF-2: baja lógica. Las órdenes, facturas y evaluaciones se prueban
    # con sus tablas (T3, T13, T15); acá, que la fila y su catálogo siguen.
    proveedor_id = _crear_proveedor(cursor)
    insumo_id = _crear_insumo(cursor, _crear_categoria(cursor))
    _registrar_insumo_suministrado(cursor, proveedor_id, insumo_id)

    cursor.execute("UPDATE proveedor SET activo = false WHERE id = %s", (proveedor_id,))

    cursor.execute("SELECT activo FROM proveedor WHERE id = %s", (proveedor_id,))
    assert cursor.fetchone() == (False,)
    cursor.execute("SELECT count(*) FROM proveedor_insumo WHERE proveedor_id = %s", (proveedor_id,))
    assert cursor.fetchone() == (1,)


def test_actualizado_en_lo_fija_la_base(cursor):
    proveedor_id = _crear_proveedor(cursor)
    cursor.execute(
        "UPDATE proveedor SET telefono = '3009999999', "
        "actualizado_en = now() - interval '5 days' WHERE id = %s",
        (proveedor_id,),
    )
    cursor.execute("SELECT actualizado_en = now() FROM proveedor WHERE id = %s", (proveedor_id,))
    assert cursor.fetchone() == (True,)


# --- proveedor_usuario (RF-4, RF-75) ---

def test_asociar_varios_usuarios_a_un_proveedor(cursor):
    proveedor_id = _crear_proveedor(cursor)
    for usuario_id in (15, 16):
        cursor.execute(
            "INSERT INTO proveedor_usuario (proveedor_id, usuario_id) VALUES (%s, %s)",
            (proveedor_id, usuario_id),
        )
    cursor.execute(
        "SELECT usuario_id FROM proveedor_usuario WHERE proveedor_id = %s ORDER BY usuario_id",
        (proveedor_id,),
    )
    assert [r[0] for r in cursor.fetchall()] == [15, 16]


def test_rechaza_asociar_un_usuario_a_un_segundo_proveedor(cursor):
    primero = _crear_proveedor(cursor, nit="900123456-7")
    segundo = _crear_proveedor(cursor, nit="800555444-1", nombre="Carnes Sur")
    cursor.execute(
        "INSERT INTO proveedor_usuario (proveedor_id, usuario_id) VALUES (%s, 15)", (primero,)
    )
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cursor.execute(
            "INSERT INTO proveedor_usuario (proveedor_id, usuario_id) VALUES (%s, 15)", (segundo,)
        )


# --- proveedor_insumo (RF-5, RF-6) ---

def test_registrar_insumo_suministrado_con_y_sin_precio_vigente(cursor):
    proveedor_id = _crear_proveedor(cursor)
    categoria_id = _crear_categoria(cursor)
    con_precio = _crear_insumo(cursor, categoria_id, nombre="Leche entera")
    sin_precio = _crear_insumo(cursor, categoria_id, nombre="Queso crema")

    _registrar_insumo_suministrado(cursor, proveedor_id, con_precio, precio_vigente=4200)
    _registrar_insumo_suministrado(cursor, proveedor_id, sin_precio)

    cursor.execute(
        "SELECT item_inventario_id, precio_vigente FROM proveedor_insumo "
        "WHERE proveedor_id = %s ORDER BY item_inventario_id",
        (proveedor_id,),
    )
    assert cursor.fetchall() == [(con_precio, 4200), (sin_precio, None)]


def test_un_proveedor_suministra_insumos_de_varias_sucursales(cursor):
    # RF-1 (común a todas las sucursales) y RF-5 (se registra insumo por
    # insumo de cada sucursal).
    proveedor_id = _crear_proveedor(cursor)
    categoria_id = _crear_categoria(cursor)
    leche_sucursal_1 = _crear_insumo(cursor, categoria_id, sucursal_id=1)
    leche_sucursal_2 = _crear_insumo(cursor, categoria_id, sucursal_id=2)

    _registrar_insumo_suministrado(cursor, proveedor_id, leche_sucursal_1)
    _registrar_insumo_suministrado(cursor, proveedor_id, leche_sucursal_2)

    cursor.execute(
        """
        SELECT i.sucursal_id FROM proveedor_insumo pi
        JOIN item_inventario i ON i.id = pi.item_inventario_id
        WHERE pi.proveedor_id = %s ORDER BY i.sucursal_id
        """,
        (proveedor_id,),
    )
    assert [r[0] for r in cursor.fetchall()] == [1, 2]


def test_rechaza_precio_vigente_negativo(cursor):
    proveedor_id = _crear_proveedor(cursor)
    insumo_id = _crear_insumo(cursor, _crear_categoria(cursor))
    with pytest.raises(psycopg2.errors.CheckViolation):
        _registrar_insumo_suministrado(cursor, proveedor_id, insumo_id, precio_vigente=-1)


def test_rechaza_registrar_dos_veces_el_mismo_insumo_para_un_proveedor(cursor):
    proveedor_id = _crear_proveedor(cursor)
    insumo_id = _crear_insumo(cursor, _crear_categoria(cursor))
    _registrar_insumo_suministrado(cursor, proveedor_id, insumo_id, precio_vigente=4200)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _registrar_insumo_suministrado(cursor, proveedor_id, insumo_id, precio_vigente=4300)


def test_rechaza_un_insumo_que_no_existe(cursor):
    proveedor_id = _crear_proveedor(cursor)
    with pytest.raises(psycopg2.errors.ForeignKeyViolation):
        _registrar_insumo_suministrado(cursor, proveedor_id, 999999999)
