# Generated by Django 2.1.7 on 2019-02-24 13:16

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('busstops', '0037_auto_20190127_2246'),
    ]

    operations = [
        migrations.AlterIndexTogether(
            name='stopusageusage',
            index_together={('stop', 'datetime')},
        ),
    ]