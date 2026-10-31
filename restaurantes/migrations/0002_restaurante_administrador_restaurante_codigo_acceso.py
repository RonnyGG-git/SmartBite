import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurantes', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurante',
            name='administrador',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='restaurantes_administrados', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='restaurante',
            name='codigo_acceso',
            field=models.CharField(editable=False, max_length=8, null=True),
        ),
    ]
