def test_conexion_basica(cursor):
    cursor.execute("SELECT 1")
    assert cursor.fetchone() == (1,)
