# Generated by Django 3.1 on 2020-09-10 13:53

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('busstops', '0006_delete_note'),
        ('vehicles', '0010_auto_20200909_0841'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='journeycode',
            unique_together={('code', 'service', 'siri_source'), ('code', 'service', 'data_source')},
        ),
    ]