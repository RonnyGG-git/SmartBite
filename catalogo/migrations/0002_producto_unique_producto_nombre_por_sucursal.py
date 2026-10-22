from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0001_initial'),
        ('restaurantes', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='producto',
            constraint=models.UniqueConstraint(fields=('nombre', 'sucursal'), name='unique_producto_nombre_por_sucursal'),
        ),
    ]
