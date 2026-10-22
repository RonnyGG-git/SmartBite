import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recetas', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productoingrediente',
            name='cantidad_requerida',
            field=models.DecimalField(decimal_places=3, error_messages={'min_value': 'La cantidad requerida debe ser mayor que cero.'}, max_digits=10, validators=[django.core.validators.MinValueValidator(Decimal('0.001'))]),
        ),
    ]
