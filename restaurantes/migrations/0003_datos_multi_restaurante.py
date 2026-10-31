import secrets

from django.db import migrations, models

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def asignar_codigos(apps, schema_editor):
    Restaurante = apps.get_model("restaurantes", "Restaurante")
    usados = set()
    for restaurante in Restaurante.objects.filter(codigo_acceso__isnull=True):
        while True:
            codigo = "".join(secrets.choice(ALFABETO) for _ in range(8))
            if codigo not in usados and not Restaurante.objects.filter(codigo_acceso=codigo).exists():
                break
        usados.add(codigo)
        restaurante.codigo_acceso = codigo
        restaurante.save(update_fields=["codigo_acceso"])


def _unico(ids):
    ids = {i for i in ids if i is not None}
    return ids.pop() if len(ids) == 1 else None


def asignar_restaurante_a_datos(apps, schema_editor):
    Restaurante = apps.get_model("restaurantes", "Restaurante")
    Categoria = apps.get_model("catalogo", "Categoria")
    Proveedor = apps.get_model("inventario", "Proveedor")
    Cliente = apps.get_model("operativo", "Cliente")

    restaurantes = list(Restaurante.objects.values_list("pk", flat=True))
    solo_uno = restaurantes[0] if len(restaurantes) == 1 else None

    for categoria in Categoria.objects.filter(restaurante__isnull=True):
        ids = categoria.productos.values_list("sucursal__restaurante_id", flat=True)
        categoria.restaurante_id = _unico(ids) or solo_uno
        categoria.save(update_fields=["restaurante"])

    for proveedor in Proveedor.objects.filter(restaurante__isnull=True):
        ids = proveedor.compras.values_list("detalles__item__sucursal__restaurante_id", flat=True)
        proveedor.restaurante_id = _unico(ids) or solo_uno
        proveedor.save(update_fields=["restaurante"])

    for cliente in Cliente.objects.filter(restaurante__isnull=True):
        ids = cliente.ordenes.values_list("mesa__sucursal__restaurante_id", flat=True)
        cliente.restaurante_id = _unico(ids) or solo_uno
        cliente.save(update_fields=["restaurante"])


class Migration(migrations.Migration):

    dependencies = [
        ("restaurantes", "0002_restaurante_administrador_restaurante_codigo_acceso"),
        ("catalogo", "0003_categoria_restaurante_alter_categoria_nombre_and_more"),
        ("inventario", "0003_proveedor_restaurante"),
        ("operativo", "0007_cliente_restaurante"),
    ]

    operations = [
        migrations.RunPython(asignar_codigos, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="restaurante",
            name="codigo_acceso",
            field=models.CharField(editable=False, max_length=8, unique=True),
        ),
        migrations.RunPython(asignar_restaurante_a_datos, migrations.RunPython.noop),
    ]
