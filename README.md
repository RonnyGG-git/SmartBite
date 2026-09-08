# Smart Bite — Django (MVT)

Migración del frontend React de `smartibite-frontend` a un proyecto Django monolítico
(Model-View-Template). El diseño completo de esta migración —apps, modelos, decisiones de
arquitectura— está documentado en el `README.md` del repo original
(`smartibite-frontend/README.md`).

## Apps

`core` (utilidades y `RoleRequiredMixin`), `cuentas` (usuarios/roles/permisos/login),
`restaurantes` (restaurantes/sucursales), `catalogo` (productos/categorías),
`inventario` (ítems, movimientos, proveedores, compras), `recetas`, `operativo`
(mesas, órdenes, QR), `caja` (pagos, ventas), `cocina`, `menu_cliente` (público, vía QR),
`reportes` (dashboard).

## Puesta en marcha

```bash
# Entorno virtual ya creado en ./venv — para reactivarlo:
venv\Scripts\activate            # Windows

pip install -r requirements.txt

python manage.py migrate
python manage.py seed_datos      # crea los 5 roles del sistema y métodos de pago
python manage.py createsuperuser
python manage.py runserver
```

Después de crear el superusuario, asígnale el rol `ADMINISTRADOR` desde `/admin/` (o por
shell) para que el sidebar y las vistas de gestión se habiliten correctamente:

```python
python manage.py shell
>>> from cuentas.models import Usuario, Rol
>>> u = Usuario.objects.get(email="tu@email.com")
>>> u.rol = Rol.objects.get(nombre="ADMINISTRADOR")
>>> u.save()
```

## Flujo probado end-to-end

Restaurante → Sucursal → Categoría → Producto → Ítem de inventario → Mesa → Compra a
proveedor (con recepción que suma stock) → Ajuste manual de stock → Crear orden → Agregar
producto a la orden → Cambiar estado → Cobrar (genera Pago, cierra la orden, libera la
mesa) → aparece en Ventas. También: QR de mesa → menú público sin login, y control de
acceso por rol (un usuario `MESERO` no puede entrar a pantallas de `ADMINISTRADOR`/`CAJERO`).

## Pendiente (fuera de alcance de esta migración)

Diseño de API (DRF), base de datos de producción (Postgres), despliegue. Ver la sección 9
del README de migración original.
