# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2016-12-15 16:17
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('dbinv', '0011_auto_20161215_1243'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='assetstatuschange',
            unique_together=set([]),
        ),
        migrations.AlterUniqueTogether(
            name='productstatuschange',
            unique_together=set([]),
        ),
    ]