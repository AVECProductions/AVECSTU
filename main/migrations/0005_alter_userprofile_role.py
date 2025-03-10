# Generated by Django 5.1.4 on 2024-12-28 16:09

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0004_invite_userprofile'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(choices=[('member', 'Member'), ('operator', 'Operator'), ('admin', 'Admin'), ('public', 'Public')], default='member', max_length=10),
        ),
    ]
