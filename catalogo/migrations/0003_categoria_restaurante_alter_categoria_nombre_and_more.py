import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0002_producto_unique_producto_nombre_por_sucursal'),
        ('restaurantes', '0002_restaurante_administrador_restaurante_codigo_acceso'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoria',
            name='restaurante',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='categorias', to='restaurantes.restaurante'),
        ),
        migrations.AlterField(
            model_name='categoria',
            name='nombre',
            field=models.CharField(max_length=100),
        ),
        migrations.AddConstraint(
            model_name='categoria',
            constraint=models.UniqueConstraint(fields=('restaurante', 'nombre'), name='unique_categoria_por_restaurante'),
        ),
    ]
