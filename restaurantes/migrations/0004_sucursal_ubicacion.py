
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurantes', '0003_datos_multi_restaurante'),
    ]

    operations = [
        migrations.AddField(
            model_name='sucursal',
            name='latitud',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, validators=[django.core.validators.MinValueValidator(-90), django.core.validators.MaxValueValidator(90)]),
        ),
        migrations.AddField(
            model_name='sucursal',
            name='longitud',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, validators=[django.core.validators.MinValueValidator(-180), django.core.validators.MaxValueValidator(180)]),
        ),
    ]
