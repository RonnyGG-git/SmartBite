import os
from pathlib import Path

import psycopg2
import pytest


def _cargar_env_test():
    """Carga sql/tests/.env.test si existe, sin pisar variables ya definidas."""
    ruta = Path(__file__).parent / ".env.test"
    if not ruta.exists():
        return
    for linea in ruta.read_text().splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


_cargar_env_test()


@pytest.fixture(scope="session")
def database_url():
    url = os.environ.get("DATABASE_URL_TEST")
    if not url:
        pytest.fail(
            "Falta la variable de entorno DATABASE_URL_TEST — ver sql/tests/README.md"
        )
    return url


TABLAS_SQL = Path(__file__).resolve().parents[1] / "TABLAS" / "SMARTBITE_INVENTARIO_SP.sql"


@pytest.fixture(scope="session")
def esquema(database_url):
    """Recrea el esquema desde cero una vez por sesión de tests, aplicando
    sql/TABLAS/SMARTBITE_INVENTARIO_SP.sql tal como se aplicaría en Neon."""
    connection = psycopg2.connect(database_url)
    connection.autocommit = True
    with connection.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        cur.execute(TABLAS_SQL.read_text(encoding="utf-8"))
    connection.close()


@pytest.fixture
def conn(database_url, esquema):
    connection = psycopg2.connect(database_url)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def cursor(conn):
    with conn.cursor() as cur:
        yield cur
