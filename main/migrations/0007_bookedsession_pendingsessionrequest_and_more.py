# Generated by Django 5.1.4 on 2025-01-07 23:47

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0006_userprofile_phone'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BookedSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('booked_date', models.DateField()),
                ('booked_start_time', models.TimeField()),
                ('duration_hours', models.PositiveIntegerField(default=1)),
                ('status', models.CharField(choices=[('booked', 'Booked'), ('paid', 'Paid'), ('canceled', 'Canceled')], default='booked', max_length=20)),
                ('notes', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('booked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='booked_sessions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='PendingSessionRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('requester_name', models.CharField(max_length=255)),
                ('requester_email', models.EmailField(max_length=254)),
                ('requester_phone', models.CharField(max_length=50)),
                ('requested_date', models.DateField()),
                ('requested_time', models.TimeField()),
                ('hours', models.PositiveIntegerField()),
                ('notes', models.TextField(blank=True, null=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('approved', 'Approved'), ('declined', 'Declined')], default='pending', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.DeleteModel(
            name='ActiveRequest',
        ),
        migrations.AddField(
            model_name='usermembership',
            name='credits',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
