from django.db import migrations
from django.db.models import OuterRef, Subquery


def rellenar_sucursal(apps, schema_editor):
    Orden = apps.get_model("operativo", "Orden")
    Mesa = apps.get_model("operativo", "Mesa")
    Orden.objects.filter(sucursal__isnull=True, mesa__isnull=False).update(
        sucursal=Subquery(Mesa.objects.filter(pk=OuterRef("mesa_id")).values("sucursal_id")[:1])
    )


class Migration(migrations.Migration):

    dependencies = [
        ("operativo", "0009_orden_sucursal_mesa_opcional"),
    ]

    operations = [
        migrations.RunPython(rellenar_sucursal, migrations.RunPython.noop),
    ]
