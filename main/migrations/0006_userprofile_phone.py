# Generated by Django 5.1.4 on 2024-12-29 19:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0005_alter_userprofile_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='phone',
            field=models.CharField(blank=True, max_length=15, null=True),
        ),
    ]
