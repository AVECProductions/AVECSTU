from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now, timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver

class ActiveRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('declined', 'Declined'),
    ]

    name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=50)
    requested_date = models.DateField()
    requested_time = models.TimeField()
    hours = models.IntegerField()
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Request by {self.name} on {self.requested_date} at {self.requested_time}"

class Operator(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.name


class MembershipPlan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    stripe_price_id = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class UserMembership(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=False)
    stripe_subscription_id = models.CharField(max_length=100, unique=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.plan.name if self.plan else 'No Plan'}"

def default_expiration():
    return now() + timedelta(days=7)

class Invite(models.Model):
    ROLE_CHOICES = (
        ('member', 'Member'),
        ('operator', 'Operator'),
    )

    email = models.EmailField(unique=True)
    token = models.CharField(max_length=64, unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    expires_at = models.DateTimeField(default=default_expiration)
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and self.expires_at > now()

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('member', 'Member'),
        ('operator', 'Operator'),
        ('admin', 'Admin'),
        ('public', 'Public'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="member")
    phone = models.CharField(max_length=15, null=True, blank=True)  # New field for phone numbers

    def __str__(self):
        return f"{self.user.username} - {self.role}"
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()