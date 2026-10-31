
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('operativo', '0010_rellenar_sucursal_orden'),
        ('restaurantes', '0003_datos_multi_restaurante'),
    ]

    operations = [
        migrations.CreateModel(
            name='LineaTelefonica',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('numero', models.CharField(max_length=20, unique=True)),
                ('activa', models.BooleanField(default=True)),
                ('numero_transferencia', models.CharField(blank=True, max_length=20)),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='lineas_telefonicas', to='restaurantes.sucursal')),
            ],
            options={
                'verbose_name': 'línea telefónica',
                'verbose_name_plural': 'líneas telefónicas',
                'ordering': ['numero'],
            },
        ),
        migrations.CreateModel(
            name='Llamada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('identificador', models.CharField(max_length=64, unique=True)),
                ('canal', models.CharField(choices=[('TELEFONO', 'Teléfono'), ('DEMO', 'Simulador')], default='TELEFONO', max_length=10)),
                ('telefono_origen', models.CharField(blank=True, max_length=20)),
                ('estado', models.CharField(choices=[('ACTIVA', 'Activa'), ('FINALIZADA', 'Finalizada'), ('CORTADA', 'Cortada por el cliente'), ('TRANSFERIDA', 'Transferida a un operador'), ('FALLIDA', 'Fallida')], default='ACTIVA', max_length=12)),
                ('fase', models.CharField(choices=[('PEDIDO', 'Tomando pedido'), ('DATOS_REGISTRADOS', 'Confirmando datos registrados'), ('NOMBRE', 'Pidiendo nombre'), ('TELEFONO', 'Pidiendo teléfono'), ('MODALIDAD', 'Pidiendo modalidad'), ('CONFIRMACION', 'Confirmando pedido'), ('CERRADA', 'Cerrada')], default='PEDIDO', max_length=20)),
                ('items', models.JSONField(blank=True, default=dict)),
                ('pendiente', models.JSONField(blank=True, default=dict)),
                ('observaciones', models.CharField(blank=True, max_length=300)),
                ('nombre_cliente', models.CharField(blank=True, max_length=150)),
                ('telefono_contacto', models.CharField(blank=True, max_length=20)),
                ('tipo_consumo', models.CharField(blank=True, max_length=15)),
                ('datos_registrados_ofrecidos', models.BooleanField(default=False)),
                ('resumen_leido', models.BooleanField(default=False)),
                ('silencios', models.PositiveSmallIntegerField(default=0)),
                ('finalizada_en', models.DateTimeField(blank=True, null=True)),
                ('error', models.CharField(blank=True, max_length=300)),
                ('cliente', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='operativo.cliente')),
                ('linea', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='llamadas', to='agente_telefonico.lineatelefonica')),
                ('orden', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='llamada_telefonica', to='operativo.orden')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='llamadas', to='restaurantes.sucursal')),
            ],
            options={
                'ordering': ['-creado_en'],
            },
        ),
        migrations.CreateModel(
            name='TurnoLlamada',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rol', models.CharField(choices=[('CLIENTE', 'Cliente'), ('AGENTE', 'Agente')], max_length=8)),
                ('texto', models.TextField(max_length=2000)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('llamada', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='turnos', to='agente_telefonico.llamada')),
            ],
            options={
                'ordering': ['creado_en', 'pk'],
            },
        ),
    ]
