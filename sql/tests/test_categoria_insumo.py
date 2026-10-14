import psycopg2
import pytest


def test_crear_categoria(cursor):
    cursor.execute(
        "INSERT INTO categoria_insumo (nombre) VALUES (%s) RETURNING id",
        ("Lácteos",),
    )
    categoria_id = cursor.fetchone()[0]
    assert categoria_id is not None


def test_rechaza_nombre_duplicado(cursor):
    cursor.execute("INSERT INTO categoria_insumo (nombre) VALUES (%s)", ("Cárnicos",))
    with pytest.raises(psycopg2.errors.UniqueViolation):
        cursor.execute("INSERT INTO categoria_insumo (nombre) VALUES (%s)", ("Cárnicos",))
