from django.db import models
from django.contrib.auth.models import User
from django.utils.timezone import now, timedelta
from django.db.models.signals import post_save
from django.dispatch import receiver

# ----------------------------------------------------------------------------------
# PENDING SESSIONS
# ----------------------------------------------------------------------------------
class PendingSessionRequest(models.Model):
    """
    Holds session requests that are not immediately confirmed.
    """
    DoesNotExist = None

    class Meta:
        db_table = "pending_sessions"

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
    ]

    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField()
    requester_phone = models.CharField(max_length=50, blank=True)
    requested_date = models.DateField()
    requested_time = models.TimeField()
    hours = models.PositiveIntegerField()
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Request by {self.requester_name} on {self.requested_date} at {self.requested_time}"


# ----------------------------------------------------------------------------------
# BOOKED SESSIONS (SOURCE OF TRUTH FOR CONFIRMED BOOKINGS)
# ----------------------------------------------------------------------------------
class BookedSession(models.Model):
    """
    Each row represents a confirmed booking on the studio calendar.
    """
    class Meta:
        db_table = "booked_sessions"

    STATUS_CHOICES = [
        ('booked', 'Booked'),
        ('paid', 'Paid'),
        ('canceled', 'Canceled'),
    ]

    booked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='booked_sessions'
    )
    booked_date = models.DateField()
    booked_start_time = models.TimeField()
    # New field
    booked_datetime = models.DateTimeField(null=True, blank=True)

    duration_hours = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='booked')
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        user_str = self.booked_by.username if self.booked_by else "Unknown"
        return f"Session on {self.booked_date} at {self.booked_start_time} by {user_str}"


# ----------------------------------------------------------------------------------
# OPERATOR (OPTIONAL TABLE)
# ----------------------------------------------------------------------------------
# If you still want a separate Operator table for extra data, keep it:
"""
class Operator(models.Model):
    class Meta:
        db_table = "operators"

    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.name
"""


# ----------------------------------------------------------------------------------
# MEMBERSHIP MODELS
# ----------------------------------------------------------------------------------
class MembershipPlan(models.Model):
    """
    Defines membership tiers or plans (e.g., monthly, annual).
    """
    class Meta:
        db_table = "membership_plan"

    name = models.CharField(max_length=100)
    stripe_product_id = models.CharField(max_length=100, default="prod_123")  # Reference to Stripe product

    def __str__(self):
        return self.name


class UserMembership(models.Model):
    """
    Each user can have a one-to-one relationship with a membership.
    """
    class Meta:
        db_table = "user_membership"

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)  # Set on explicit end (optional)
    active = models.BooleanField(default=False)
    stripe_subscription_id = models.CharField(max_length=100, unique=True, null=True)

    credits = models.PositiveIntegerField(default=0)
    next_billing_date = models.DateField(null=True, blank=True)  # Next payment due date
    valid_until = models.DateField(null=True, blank=True)  # Membership valid until this date

    def __str__(self):
        plan_name = self.plan.name if self.plan else 'No Plan'
        return f"{self.user.username} - {plan_name}"



# ----------------------------------------------------------------------------------
# INVITES
# ----------------------------------------------------------------------------------
def default_expiration():
    return now() + timedelta(days=7)

class Invite(models.Model):
    """
    Manages invitation tokens for role-based onboarding.
    """
    class Meta:
        db_table = "invite"

    # Currently only these two. If you want to invite admins, add ('admin', 'Admin').
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

    def __str__(self):
        return f"Invite for {self.email} (role={self.role})"


# ----------------------------------------------------------------------------------
# USER PROFILE (SINGLE ROLE & PHONE)
# ----------------------------------------------------------------------------------
class UserProfile(models.Model):
    """
    Extends the built-in User model with a single role and phone.
    """
    class Meta:
        db_table = "user_profile"

    ROLE_CHOICES = (
        ('public', 'Public'),
        ('member', 'Member'),
        ('operator', 'Operator'),
        ('admin', 'Admin'),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="public"  # or "member", depending on your default
    )
    phone = models.CharField(max_length=15, null=True, blank=True)
    stripe_customer_id = models.CharField(max_length=255, unique=True, null=True, blank=True)  # Add this field

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    def has_minimum_role(self, required_role):
        """
        Utility that returns True if this user's role is >= the required role in hierarchy.
        """
        role_priority = {
            'public': 1,
            'member': 2,
            'operator': 3,
            'admin': 4,
        }
        return role_priority[self.role] >= role_priority[required_role]


# ----------------------------------------------------------------------------------
# CREATE / SAVE USER PROFILE SIGNALS
# ----------------------------------------------------------------------------------
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
