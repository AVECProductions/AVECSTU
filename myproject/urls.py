from django.contrib import admin
from django.urls import path
from main.views import *

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('monthly-calendar/', monthly_calendar_view, name='monthly_calendar'),
    path('daily-scheduler/', daily_scheduler_view, name='daily_scheduler'),
    path('reservation/', reservation_form_view, name='reservation_form'),
    path('operator-dashboard/', operator_dashboard_view, name='operator_dashboard'),
    path('accounts/login/', member_login_view, name='member_login'),
    path('guest-login/', guest_login_view, name='guest_login'),
    path('member-logout/', member_logout_view, name='member_logout'),
    path('payment-success/', payment_success, name='payment_success'),
    path('stripe-webhook/', stripe_webhook, name='stripe_webhook')
]
