from django.contrib import admin
from django.urls import path
from main.views import *
from decouple import config
from django.contrib.auth import views as auth_views
from main.payments import stripe_webhook

urlpatterns = [
    path(config('ADMIN_URL'), admin.site.urls),
    path('', home_view, name='home'),
    path('monthly-calendar/', monthly_calendar_view, name='monthly_calendar'),
    path('daily-scheduler/', daily_scheduler_view, name='daily_scheduler'),
    path('reservation/', reservation_form_view, name='reservation_form'),
    path('operator-dashboard/', operator_dashboard_view, name='operator_dashboard'),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='mobile/member_login.html'), name='member_login'),
    path('guest-login/', guest_login_view, name='guest_login'),
    path('member-logout/', member_logout_view, name='member_logout'),
    path('payment-success/', payment_success, name='payment_success'),
    path(config('WEBHOOK_URL'), stripe_webhook, name='stripe_webhook'),
    path('create-invite/', create_invite_view, name='create_invite'),
    path('register/<str:token>/', register_view, name='register'),
    path('member-dashboard/', member_dashboard_view, name='member_dashboard'),
    path("admin-dashboard/", admin_dashboard, name="admin_dashboard"),
    path("pay-membership/", pay_membership, name="pay_membership"),
    path("cancel-membership/", cancel_membership, name="cancel_membership"),
    path('session-manager/', session_manager_view, name='session_manager'),
    path('member-profile/', member_profile, name='member_profile'),
    path("membership-management/", membership_management_view, name="membership_management"),
]