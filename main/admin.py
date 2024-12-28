from django.contrib import admin
from .models import ActiveRequest, Operator
from .models import UserProfile

admin.site.register(ActiveRequest)
admin.site.register(Operator)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username", "user__email")
