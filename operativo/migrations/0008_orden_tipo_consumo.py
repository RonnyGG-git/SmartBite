from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operativo', '0007_cliente_restaurante'),
    ]

    operations = [
        migrations.AddField(
            model_name='orden',
            name='tipo_consumo',
            field=models.CharField(choices=[('EN_RESTAURANTE', 'Comer en el restaurante'), ('PARA_LLEVAR', 'Para llevar')], default='EN_RESTAURANTE', max_length=15),
        ),
    ]
