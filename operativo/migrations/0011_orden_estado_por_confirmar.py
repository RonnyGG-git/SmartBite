
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operativo', '0010_rellenar_sucursal_orden'),
    ]

    operations = [
        migrations.AlterField(
            model_name='orden',
            name='estado',
            field=models.CharField(choices=[('POR_CONFIRMAR', 'Por confirmar'), ('PENDIENTE', 'Pendiente'), ('EN_PREPARACION', 'En preparación'), ('LISTA', 'Lista'), ('ENTREGADA', 'Entregada'), ('CANCELADA', 'Cancelada')], default='PENDIENTE', max_length=15),
        ),
    ]
