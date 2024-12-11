# Generated by Django 5.1.4 on 2024-12-11 14:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='activerequest',
            name='status',
            field=models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('paid', 'Paid'), ('declined', 'Declined')], default='pending', max_length=20),
        ),
    ]