# Generated by Django 5.1.6 on 2025-03-04 14:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0013_remove_membershipplan_price_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='usermembership',
            name='stripe_subscription_id',
            field=models.CharField(blank=True, max_length=100, null=True, unique=True),
        ),
    ]
