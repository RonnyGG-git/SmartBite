import psycopg2
import pytest


def _crear_categoria(cursor, nombre="Lácteos"):
    cursor.execute(
        "INSERT INTO categoria_insumo (nombre) VALUES (%s) RETURNING id", (nombre,)
    )
    return cursor.fetchone()[0]


def _set_usuario_actual(cursor, usuario_id):
    cursor.execute(f"SET LOCAL app.usuario_actual = {int(usuario_id)}")


def _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche entera", **overrides):
    columnas = dict(
        nombre=nombre,
        unidad_medida=overrides.pop("unidad_medida", "L"),
        categoria_id=categoria_id,
        sucursal_id=sucursal_id,
        **overrides,
    )
    campos = ", ".join(columnas.keys())
    placeholders = ", ".join(["%s"] * len(columnas))
    cursor.execute(
        f"INSERT INTO item_inventario ({campos}) VALUES ({placeholders}) RETURNING id",
        list(columnas.values()),
    )
    return cursor.fetchone()[0]


def test_crear_insumo_valido(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    assert insumo_id is not None


def test_rechaza_nombre_duplicado_en_misma_sucursal_sin_importar_mayusculas(cursor):
    categoria_id = _crear_categoria(cursor)
    _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche Entera")
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="  leche entera  ")


def test_permite_mismo_nombre_en_otra_sucursal(cursor):
    categoria_id = _crear_categoria(cursor)
    _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche entera")
    otro_id = _crear_insumo(cursor, categoria_id, sucursal_id=2, nombre="Leche entera")
    assert otro_id is not None


def test_rechaza_stock_negativo(cursor):
    categoria_id = _crear_categoria(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_insumo(cursor, categoria_id, stock_actual=-1)


def test_desactivar_insumo(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))
    cursor.execute("SELECT activo FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone() == (False,)


def test_rechaza_redesactivar_insumo_ya_inactivo(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))


def test_rechaza_insumo_sin_categoria(cursor):
    with pytest.raises(psycopg2.errors.NotNullViolation):
        cursor.execute(
            "INSERT INTO item_inventario (nombre, unidad_medida, sucursal_id) "
            "VALUES (%s, %s, %s)",
            ("Insumo sin categoría", "unidad", 1),
        )


def test_configurar_stock_minimo_por_insumo(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    _set_usuario_actual(cursor, 1)
    cursor.execute(
        "UPDATE item_inventario SET stock_minimo = 12 WHERE id = %s", (insumo_id,)
    )
    cursor.execute("SELECT stock_minimo FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone() == (12,)


def test_consultar_insumos_filtrando_por_nombre(cursor):
    categoria_id = _crear_categoria(cursor)
    _crear_insumo(cursor, categoria_id, nombre="Leche entera")
    _crear_insumo(cursor, categoria_id, nombre="Queso crema")

    cursor.execute("SELECT nombre FROM item_inventario WHERE nombre = %s", ("Leche entera",))
    assert [r[0] for r in cursor.fetchall()] == ["Leche entera"]


def test_consultar_insumos_filtrando_por_categoria_estado_y_sucursal(cursor):
    categoria_id = _crear_categoria(cursor)
    otra_categoria_id = _crear_categoria(cursor, nombre="Cárnicos")
    _crear_insumo(cursor, categoria_id, sucursal_id=1, nombre="Leche")
    _crear_insumo(cursor, otra_categoria_id, sucursal_id=1, nombre="Carne")
    _crear_insumo(cursor, categoria_id, sucursal_id=2, nombre="Leche")

    cursor.execute(
        """
        SELECT nombre FROM item_inventario
        WHERE categoria_id = %s AND sucursal_id = %s AND activo = true
        """,
        (categoria_id, 1),
    )
    assert [r[0] for r in cursor.fetchall()] == ["Leche"]


def test_editar_insumo_inactivo_no_se_confunde_con_redesactivarlo(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    _set_usuario_actual(cursor, 1)
    cursor.execute("UPDATE item_inventario SET activo = false WHERE id = %s", (insumo_id,))
    cursor.execute(
        "UPDATE item_inventario SET descripcion = %s WHERE id = %s",
        ("Typo corregido", insumo_id),
    )
    cursor.execute("SELECT descripcion, activo FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone() == ("Typo corregido", False)


def test_rechaza_crear_insumo_con_stock_inicial(cursor):
    categoria_id = _crear_categoria(cursor)
    with pytest.raises(psycopg2.errors.RaiseException):
        _crear_insumo(cursor, categoria_id, stock_actual=50)


def test_rechaza_modificar_stock_sin_movimiento(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    _set_usuario_actual(cursor, 1)
    with pytest.raises(psycopg2.errors.RaiseException):
        cursor.execute(
            "UPDATE item_inventario SET stock_actual = 500 WHERE id = %s", (insumo_id,)
        )


@pytest.mark.parametrize("campo", ["costo_unitario", "stock_minimo", "dias_alerta_vencimiento"])
def test_rechaza_valores_negativos(cursor, campo):
    categoria_id = _crear_categoria(cursor)
    with pytest.raises(psycopg2.errors.CheckViolation):
        _crear_insumo(cursor, categoria_id, **{campo: -1})


def test_actualizado_en_lo_fija_la_base_en_cada_edicion(cursor):
    categoria_id = _crear_categoria(cursor)
    insumo_id = _crear_insumo(cursor, categoria_id)
    _set_usuario_actual(cursor, 1)
    cursor.execute(
        "UPDATE item_inventario SET descripcion = 'x', "
        "actualizado_en = now() - interval '5 days' WHERE id = %s",
        (insumo_id,),
    )
    cursor.execute("SELECT actualizado_en = now() FROM item_inventario WHERE id = %s", (insumo_id,))
    assert cursor.fetchone() == (True,)
