# Tests del esquema SQL de Inventario

Prueban las tablas, triggers y constraints de `sql/TABLAS/` contra una base
Postgres real de prueba — sin mocks (plan.md, "Estrategia de tests").

## Puesta en marcha

```bash
pip install -r sql/tests/requirements-test.txt
export DATABASE_URL_TEST="postgres://usuario:password@host/basededatos"
pytest sql/tests
```

`DATABASE_URL_TEST` debe apuntar a una **rama o base de desarrollo de Neon**,
nunca a la base real del equipo (constitución, principio 7). No se
commitea — expórtala en tu shell o guárdala en un `.env` local
(`.gitignore` ya lo excluye).
