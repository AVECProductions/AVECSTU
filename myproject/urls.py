from django.contrib import admin
from django.urls import path
from main.views import *

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', login_view, name='login'),
    path('home/', home_view, name='home'),
    path('week-scheduler/', week_scheduler_view, name='week_scheduler'),
    path('reservation/', reservation_form_view, name='reservation_form'),
    path('operator-dashboard/', operator_dashboard_view, name='operator_dashboard'),
    path('member-login/', member_login_view, name='member_login'),
    path('member-logout/', member_logout_view, name='member_logout'),
]
