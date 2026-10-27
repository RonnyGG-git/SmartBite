from pathlib import Path

INSERTS_SQL = Path(__file__).resolve().parents[1] / "INSERTS" / "SMARTBITE_INVENTARIO_SP.sql"

CATEGORIAS_ESPERADAS = {
    "Lácteos", "Cárnicos", "Panadería", "Bebidas",
    "Frutas y Verduras", "Abarrotes", "Limpieza", "Desechables",
}


def test_seed_categorias_corre_limpio_y_crea_las_esperadas(cursor):
    cursor.execute(INSERTS_SQL.read_text(encoding="utf-8"))
    cursor.execute("SELECT nombre FROM categoria_insumo")
    nombres = {r[0] for r in cursor.fetchall()}
    assert CATEGORIAS_ESPERADAS <= nombres


def test_seed_categorias_es_idempotente(cursor):
    # No se compara contra un conteo total fijo: otros tests (los de
    # concurrencia de T7/T10) usan conexiones con autocommit=True y dejan
    # categorías propias committeadas de verdad en la sesión compartida.
    cursor.execute(INSERTS_SQL.read_text(encoding="utf-8"))
    cursor.execute("SELECT COUNT(*) FROM categoria_insumo")
    primera_vez = cursor.fetchone()[0]

    cursor.execute(INSERTS_SQL.read_text(encoding="utf-8"))
    cursor.execute("SELECT COUNT(*) FROM categoria_insumo")
    segunda_vez = cursor.fetchone()[0]

    assert primera_vez == segunda_vez
