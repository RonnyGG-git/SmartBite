import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuentas', '0001_initial'),
        ('restaurantes', '0002_restaurante_administrador_restaurante_codigo_acceso'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='restaurante',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='empleados', to='restaurantes.restaurante'),
        ),
    ]
