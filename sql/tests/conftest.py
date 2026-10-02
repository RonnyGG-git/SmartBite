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


TABLAS_DIR = Path(__file__).resolve().parents[1] / "TABLAS"

# En este orden: Compras usa tablas y funciones de Inventario.
SCRIPTS_TABLAS = [
    TABLAS_DIR / "SMARTBITE_INVENTARIO_SP.sql",
    TABLAS_DIR / "SMARTBITE_COMPRAS_SP.sql",
]


@pytest.fixture(scope="session")
def esquema(database_url):
    """Recrea el esquema desde cero una vez por sesión de tests, aplicando
    los scripts de sql/TABLAS/ en orden, tal como se aplicarían en Neon."""
    connection = psycopg2.connect(database_url)
    connection.autocommit = True
    with connection.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        for script in SCRIPTS_TABLAS:
            cur.execute(script.read_text(encoding="utf-8"))
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
