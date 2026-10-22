import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operativo', '0006_merge_20261021_1137'),
        ('restaurantes', '0002_restaurante_administrador_restaurante_codigo_acceso'),
    ]

    operations = [
        migrations.AddField(
            model_name='cliente',
            name='restaurante',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='clientes', to='restaurantes.restaurante'),
        ),
    ]
