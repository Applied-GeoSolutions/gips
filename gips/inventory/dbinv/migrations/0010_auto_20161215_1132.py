# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2016-12-15 11:32
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import gips.inventory.dbinv.models


class Migration(migrations.Migration):

    dependencies = [
        ('dbinv', '0009_delete_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='AssetDependency',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dbinv.Asset')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dbinv.Product')),
            ],
        ),
        migrations.CreateModel(
            name='AssetStatusChange',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.TextField(validators=[gips.inventory.dbinv.models.valid_status])),
                ('time', models.DateTimeField(auto_now_add=True)),
                ('asset', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dbinv.Asset')),
            ],
        ),
        migrations.CreateModel(
            name='ProductStatusChange',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.TextField(validators=[gips.inventory.dbinv.models.valid_status])),
                ('time', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dbinv.Asset')),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='productstatuschange',
            unique_together=set([('product', 'status')]),
        ),
        migrations.AlterUniqueTogether(
            name='assetstatuschange',
            unique_together=set([('asset', 'status')]),
        ),
        migrations.AlterUniqueTogether(
            name='assetdependency',
            unique_together=set([('product', 'asset')]),
        ),
    ]
