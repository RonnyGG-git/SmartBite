from pathlib import Path

import psycopg2
import pytest

COMPRAS_SQL = Path(__file__).resolve().parents[1] / "TABLAS" / "SMARTBITE_COMPRAS_SP.sql"


def test_compras_exige_aplicar_primero_el_esquema_de_inventario(cursor):
    # Compras usa tablas y funciones de Inventario. Sobre un esquema vacío
    # tiene que fallar al principio y con un mensaje claro, no a mitad del
    # script con un "relation does not exist".
    cursor.execute("CREATE SCHEMA esquema_vacio_t1")
    cursor.execute("SET LOCAL search_path TO esquema_vacio_t1")
    with pytest.raises(psycopg2.errors.RaiseException, match="aplicar primero"):
        cursor.execute(COMPRAS_SQL.read_text(encoding="utf-8"))
