from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('operativo', '0001_initial'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='cliente',
            unique_together={('nombre', 'telefono', 'email')},
        ),
    ]
