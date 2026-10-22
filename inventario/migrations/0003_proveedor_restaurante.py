import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0002_iteminventario_activo_iteminventario_categoria_and_more'),
        ('restaurantes', '0002_restaurante_administrador_restaurante_codigo_acceso'),
    ]

    operations = [
        migrations.AddField(
            model_name='proveedor',
            name='restaurante',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='proveedores', to='restaurantes.restaurante'),
        ),
    ]
