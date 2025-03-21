from django.contrib import admin
from django.urls import path
from django.views.generic.base import RedirectView
from django.contrib.staticfiles.storage import staticfiles_storage
from main.views import *
from decouple import config
from django.contrib.auth import views as auth_views
from main.payments_subscription import stripe_webhook

urlpatterns = [
    path(config('ADMIN_URL'), admin.site.urls),
    path('', home_view, name='home'),
    path('monthly-calendar/', monthly_calendar_view, name='monthly_calendar'),
    path('daily-scheduler/', daily_scheduler_view, name='daily_scheduler'),
    path('reservation/', reservation_form_view, name='reservation_form'),
    path('operator-dashboard/', operator_dashboard_view, name='operator_dashboard'),
    path('operator-console/', operator_console_view, name='operator_console'),
    path('accounts/login/', member_login_view, name='member_login'),
    path('accounts/logout/', member_logout_view, name='member_logout'),
    path('guest-login/', guest_login_view, name='guest_login'),
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
    path('customer-portal/', customer_portal_view, name='customer_portal'),
    path('apple-touch-icon.png', 
         RedirectView.as_view(url=staticfiles_storage.url('apple-touch-icon.png'))),
    path('apple-touch-icon-precomposed.png', 
         RedirectView.as_view(url=staticfiles_storage.url('apple-touch-icon.png'))),
    path('apple-touch-icon-120x120.png', 
         RedirectView.as_view(url=staticfiles_storage.url('apple-touch-icon.png'))),
    path('apple-touch-icon-120x120-precomposed.png', 
         RedirectView.as_view(url=staticfiles_storage.url('apple-touch-icon.png'))),
    path('favicon.ico', 
         RedirectView.as_view(url=staticfiles_storage.url('favicon.png'))),
]