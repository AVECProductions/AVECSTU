# Generated by Django 5.1.4 on 2025-01-10 22:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0010_bookedsession_booked_datetime'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermembership',
            name='next_billing_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='usermembership',
            name='valid_until',
            field=models.DateField(blank=True, null=True),
        ),
    ]
