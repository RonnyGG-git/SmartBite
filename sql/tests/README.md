# Tests del esquema SQL (Inventario y Compras)

Prueban las tablas, triggers y constraints de `sql/TABLAS/` contra una base
Postgres real de prueba, sin mocks: los triggers solo existen en Postgres.

## Puesta en marcha

```bash
pip install -r sql/tests/requirements-test.txt
export DATABASE_URL_TEST="postgres://usuario:password@host/basededatos"
pytest sql/tests
```

`DATABASE_URL_TEST` debe apuntar a una **rama o base de desarrollo de Neon**,
nunca a la base real del equipo: el fixture `esquema` borra y recrea el
esquema `public` en cada corrida. No se commitea — expórtala en tu shell o
guárdala en `sql/tests/.env.test` (`.gitignore` ya lo excluye).

## Orden de los scripts

El fixture aplica `SMARTBITE_INVENTARIO_SP.sql` y después
`SMARTBITE_COMPRAS_SP.sql`: Compras usa tablas y funciones de Inventario, y
si se corre solo, se corta al principio con un mensaje que lo indica. Para
cargar el esquema a mano en otra base, respetar el mismo orden.
