
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operativo', '0008_orden_tipo_consumo'),
        ('restaurantes', '0003_datos_multi_restaurante'),
    ]

    operations = [
        migrations.AddField(
            model_name='orden',
            name='sucursal',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ordenes', to='restaurantes.sucursal'),
        ),
        migrations.AlterField(
            model_name='orden',
            name='mesa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='ordenes', to='operativo.mesa'),
        ),
        migrations.AlterField(
            model_name='orden',
            name='origen',
            field=models.CharField(choices=[('MESERO', 'Mesero'), ('AUTOPEDIDO', 'Autopedido (QR)'), ('AGENTE_TELEFONICO', 'Agente telefónico')], default='MESERO', max_length=20),
        ),
    ]
