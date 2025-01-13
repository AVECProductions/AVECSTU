from django.contrib import admin
from .models import (
    PendingSessionRequest,
    BookedSession,
    # Operator,  # If you no longer need it, comment out or remove
    UserProfile,
    MembershipPlan,
    UserMembership
)

@admin.register(PendingSessionRequest)
class PendingSessionRequestAdmin(admin.ModelAdmin):
    list_display = (
        "requester_name",
        "requested_date",
        "requested_time",
        "hours",
        "status",
        "created_at",
    )
    list_filter = ("status", "requested_date", "created_at")
    search_fields = ("requester_name", "requester_email")


@admin.register(BookedSession)
class BookedSessionAdmin(admin.ModelAdmin):
    list_display = (
        "booked_by",
        "booked_date",
        "booked_start_time",
        "duration_hours",
        "status",
        "created_at",
    )
    list_filter = ("status", "booked_date", "created_at")
    search_fields = ("booked_by__username",)


# If you still have a separate Operator table, uncomment these:
"""
@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ("name", "email")
    search_fields = ("name", "email")
"""


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")


@admin.register(MembershipPlan)
class MembershipPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "stripe_product_id")
    search_fields = ("name",)


@admin.register(UserMembership)
class UserMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "active", "credits", "start_date", "end_date")
    list_filter = ("active", "start_date", "end_date")
    search_fields = ("user__username", "plan__name")
