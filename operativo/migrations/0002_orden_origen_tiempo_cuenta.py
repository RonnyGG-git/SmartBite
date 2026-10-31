from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operativo', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='orden',
            name='cuenta_solicitada_en',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orden',
            name='origen',
            field=models.CharField(choices=[('MESERO', 'Mesero'), ('AUTOPEDIDO', 'Autopedido (QR)')], default='MESERO', max_length=12),
        ),
        migrations.AddField(
            model_name='orden',
            name='preparacion_iniciada_en',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orden',
            name='tiempo_estimado_min',
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
