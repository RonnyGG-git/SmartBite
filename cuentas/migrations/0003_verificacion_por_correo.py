import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cuentas', '0002_usuario_restaurante'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='email_verificado',
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name='CodigoVerificacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                ('proposito', models.CharField(choices=[('REGISTRO', 'Verificar correo'), ('RECUPERACION', 'Recuperar contraseña')], max_length=20)),
                ('huella', models.CharField(max_length=64)),
                ('expira_en', models.DateTimeField()),
                ('intentos', models.PositiveSmallIntegerField(default=0)),
                ('usado', models.BooleanField(default=False)),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='codigos', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-creado_en', '-pk'],
                'indexes': [models.Index(fields=['usuario', 'proposito', 'usado'], name='cuentas_cod_usuario_e7c4a3_idx')],
            },
        ),
    ]
