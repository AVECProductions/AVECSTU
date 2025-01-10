from django.shortcuts import render, redirect, get_object_or_404
from django.core.mail import send_mail, EmailMessage
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.utils.timezone import localtime, now, timedelta
from django.utils.crypto import get_random_string
from django.conf import settings
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from .payments import send_rejection_email, send_payment_email_stripe, send_cancelation_confirmation_email

import stripe
import calendar
from datetime import datetime
import requests

# Forms (if any)
from .forms import ProfileUpdateForm

# Models
from .models import (
    PendingSessionRequest,       # REPLACES old 'ActiveRequest'
    BookedSession,
    Invite,
    UserMembership,
    UserProfile,
)

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
BASE_URL = settings.DOMAIN  # e.g., "https://yourdomain.com"

# ------------------------------------------
# ROLE-BASED DECORATOR
# ------------------------------------------
def role_required(role):
    """
    A decorator restricting access to a particular role
    (e.g., operator, admin). If mismatch, returns 403.
    """
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.profile.has_minimum_role(role):
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden("You do not have permission to access this page.")
        return _wrapped_view
    return decorator


# ------------------------------------------
# MEMBER DASHBOARD & MEMBERSHIP
# ------------------------------------------
@login_required
def member_dashboard_view(request):
    """
    Display the Member Dashboard with options to Update Profile,
    Manage Membership, and access the Session Manager.
    """
    context = {
        "current_time": now(),
    }
    return render(request, "member/dashboard.html", context)

@login_required
def member_profile(request):
    """
    Display the member's profile information and allow edits.
    Restricts access for 'public' users.
    """
    if request.user.profile.role == "public":
        return HttpResponseForbidden("You are not authorized to access this page.")

    if request.method == "POST":
        # Update user profile info
        user_profile = request.user.profile
        user_profile.first_name = request.POST.get("first_name", user_profile.user.first_name)
        user_profile.last_name = request.POST.get("last_name", user_profile.user.last_name)
        user_profile.email = request.POST.get("email", user_profile.user.email)
        user_profile.phone = request.POST.get("phone", user_profile.user.email)
        user_profile.save()

        # Update Django's User model
        user = request.user
        user.first_name = request.POST.get("first_name", user.first_name)
        user.last_name = request.POST.get("last_name", user.last_name)
        user.email = request.POST.get("email", user.email)
        user.save()

        messages.success(request, "Your profile has been updated.")
        return redirect("member_profile")

    # Check membership
    try:
        membership = request.user.usermembership
        membership_status = "Paid" if membership.active else "Unpaid"
    except UserMembership.DoesNotExist:
        membership_status = "Unpaid"

    context = {
        'membership_status': membership_status,
    }
    return render(request, "member/profile.html", context)

@login_required
def membership_management_view(request):
    """
    Allows members to view and manage their membership status.
    """
    # Retrieve the user's membership status
    try:
        membership = request.user.usermembership
        membership_status = "Paid" if membership.active else "Unpaid"
    except UserMembership.DoesNotExist:
        membership_status = "Unpaid"

    context = {
        "membership_status": membership_status,
    }
    return render(request, "member/membership_management.html", context)

@login_required
def session_manager_view(request):
    """
    Allows members to manage their booked sessions.
    They can view and cancel their own bookings.
    """
    user = request.user

    # Get the current time
    current_time = now()

    # Combine booked_date and booked_start_time into a datetime for comparison
    booked_sessions = BookedSession.objects.filter(
        booked_by=user,
        status='booked',
        booked_datetime__gte=now()
    ).order_by('booked_datetime')

    if request.method == "POST":
        session_id = request.POST.get('session_id')

        if session_id:
            try:
                booked_session = BookedSession.objects.get(id=session_id, booked_by=user)
                booked_session.status = "canceled"  # Mark the session as canceled
                booked_session.save()
                messages.success(request, "Session successfully canceled.")
            except BookedSession.DoesNotExist:
                messages.error(request, "Session could not be found.")
            except Exception as e:
                print(f"Error canceling the session: {e}")
                messages.error(request, "An error occurred while canceling the session.")

        return redirect('session_manager')

    context = {'booked_sessions': booked_sessions}
    return render(request, 'member/session_manager.html', context)

# ------------------------------------------
# Membership management
# ------------------------------------------

@login_required
def pay_membership(request):
    """
    Redirects the user to Stripe Checkout for membership payment.
    """
    user = request.user

    # Stripe price ID for the membership (replace with your actual price ID)
    stripe_price_id = "price_1Qaizu08vvVeCKwuAKr9zXca"

    try:
        # Create a Stripe Checkout session
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[
                {
                    'price': stripe_price_id,
                    'quantity': 1,
                },
            ],
            metadata={
                'user_id': user.id,  # Include user information for webhook handling
            },
            success_url=request.build_absolute_uri('/membership-management/'),
            cancel_url=request.build_absolute_uri('/membership-management/'),
        )

        # Redirect to Stripe Checkout
        return redirect(checkout_session.url, code=303)

    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        print("error")
        return redirect("membership_management")

def cancel_membership(request):
    """
    Cancels the user's membership and the associated Stripe subscription.
    """
    user = request.user

    try:
        # Retrieve the user's membership
        membership = user.usermembership

        # Check if the membership is active
        if membership.active and membership.stripe_subscription_id:
            # Cancel the subscription on Stripe
            success = cancel_stripe_subscription(user)
            if success:
                # Update membership status in the database
                membership.active = False
                membership.stripe_subscription_id = None
                membership.save()

                # Optionally send a cancellation confirmation email
                send_cancelation_confirmation_email(user)

                messages.success(request, "Your membership has been successfully canceled.")
            else:
                messages.error(request, "There was an issue canceling your membership. Please try again.")
        else:
            messages.error(request, "You do not have an active membership to cancel.")

    except UserMembership.DoesNotExist:
        messages.error(request, "You do not have a membership to cancel.")

    return redirect("membership_management")

def cancel_stripe_subscription(user):
    """
    Cancels the user's Stripe subscription.
    Args:
        user: The user whose subscription needs to be canceled.

    Returns:
        bool: True if the subscription was successfully canceled, False otherwise.
    """
    try:
        # Get the user's membership
        membership = UserMembership.objects.get(user=user)

        # Check if the membership has an active Stripe subscription
        if membership.stripe_subscription_id:
            # Use Stripe API to delete the subscription
            stripe.Subscription.delete(membership.stripe_subscription_id)

            # Update the membership status
            membership.active = False
            membership.stripe_subscription_id = None
            membership.save()

            return True  # Cancellation was successful
        else:
            return False  # No active subscription to cancel
    except UserMembership.DoesNotExist:
        print(f"Membership does not exist for user {user.username}.")
        return False
    except stripe.error.StripeError as e:
        print(f"Stripe error during subscription cancellation: {e}")
        return False



# ------------------------------------------
# HOME & AUTHENTICATION
# ------------------------------------------
def home_view(request):
    """
    Public home page (not password protected).
    Shows different dashboard options based on user roles.
    """
    user = request.user
    is_operator = False
    is_member = False

    if user.is_authenticated:
        profile = getattr(user, "profile", None)
        if profile:
            is_operator = profile.has_minimum_role("operator")
            is_member = profile.has_minimum_role("member")

    context = {
        'is_logged_in': user.is_authenticated,
        'is_operator': is_operator,
        'is_member': is_member,
        'current_time': now(),
    }
    return render(request, 'mobile/home.html', context)


def member_login_view(request):
    """
    Standard Django authentication (username/password).
    """
    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            return redirect('home')
        else:
            error = "Invalid credentials. Please try again."

    return render(request, 'mobile/member_login.html', {'error': error})


def guest_login_view(request):
    """
    Allows a user to log in as 'public' via a shared password.
    """
    error = None
    if request.method == "POST":
        guest_password = request.POST.get("password")

        user = authenticate(username="public", password=guest_password)
        if user:
            login(request, user)
            return redirect("reservation_form")
        else:
            error = "Guest login failed. Please try again."

    return render(request, "mobile/guest_login.html", {"error": error})


@login_required
def member_logout_view(request):
    logout(request)
    return redirect('home')


# ------------------------------------------
# RESERVATION FORM (PendingSessionRequest)
# ------------------------------------------
@login_required
def reservation_form_view(request):
    """
    Allows guests or members to submit a session request.
    For members who do not have auto-booking privileges (or if code not yet added),
    it creates a PendingSessionRequest.
    """
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        date = request.GET.get("date")
        time_ = request.GET.get("time")
        hours = request.POST.get("hours", 1)
        notes = request.POST.get("notes", "")

        print(f"Date received from form: {date}")

        # Validate date/time
        if not date or not time_:
            messages.error(request, "Date or time was not provided.")
            return redirect("reservation_form")

        try:
            requested_date = datetime.strptime(date, "%Y-%m-%d").date()
            requested_time = datetime.strptime(time_, "%H:%M").time()
        except ValueError:
            messages.error(request, "Invalid date/time format.")
            return redirect("reservation_form")

        # Create a PendingSessionRequest
        new_request = PendingSessionRequest.objects.create(
            requester_name=name,
            requester_email=email,
            requester_phone=phone,
            requested_date=requested_date,
            requested_time=requested_time,
            hours=hours,
            notes=notes,
            status="pending",
        )

        # Notify all operators (assuming you have a Django Group named "Operator", or filter by role)
        operators = User.objects.filter(groups__name="Operator")
        operator_emails = [op.email for op in operators if op.email]

        if operator_emails:
            email_content = f"""
            <div style="font-family: Arial, sans-serif; color: #333; line-height: 1.5; max-width: 600px; margin: auto;">
                <h2 style="color: #000;">New Reservation Request</h2>
                <p>A new reservation request has been submitted with the following details:</p>
                <ul style="padding-left: 20px; color: #555;">
                    <li><strong>Name:</strong> {name}</li>
                    <li><strong>Email:</strong> {email}</li>
                    <li><strong>Phone:</strong> {phone}</li>
                    <li><strong>Date:</strong> {date}</li>
                    <li><strong>Time:</strong> {time_}</li>
                    <li><strong>Duration:</strong> {hours} hour(s)</li>
                    <li><strong>Notes:</strong> {notes or 'No additional notes'}</li>
                </ul>
                <p>Click the button below to review this request in the Operator Dashboard:</p>
                <div style="text-align: center; margin: 20px 0;">
                    <a href="{settings.BASE_URL}/operator-dashboard/"
                       style="background-color: #007bff; color: #fff; text-decoration: none; padding: 10px 20px; border-radius: 5px; font-size: 16px;">
                        View Operator Dashboard
                    </a>
                </div>
                <p style="color: #777;">Thank you,</p>
                <p style="color: #777;"><strong>AVEC Studios</strong></p>
            </div>
            """

            msg = EmailMessage(
                subject="New Reservation Request Submitted",
                body=email_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=operator_emails
            )
            msg.content_subtype = "html"
            msg.send()

        messages.success(request, "Your reservation request has been submitted.")
        return redirect("home")

    return render(request, "mobile/reservation_form.html")


# ------------------------------------------
# MONTHLY CALENDAR
# ------------------------------------------
def monthly_calendar_view(request):
    """
    Shows a monthly calendar.
    Limits to 2 months in the future.
    """
    today = localtime(now()).date()
    two_months_from_now = today + timedelta(days=60)

    year = request.GET.get("year")
    month = request.GET.get("month")

    if year and month:
        try:
            year = int(year)
            month = int(month)
        except ValueError:
            year = today.year
            month = today.month
    else:
        year = today.year
        month = today.month

    requested_date = today.replace(year=year, month=month, day=1)

    # Bounds
    if requested_date < today.replace(day=1):
        return redirect('monthly_calendar')
    elif requested_date > two_months_from_now.replace(day=1):
        return redirect(f'/monthly-calendar/?year={two_months_from_now.year}&month={two_months_from_now.month}')

    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.itermonthdates(year, month)

    days_to_display = []
    for day in month_days:
        in_current_month = (day.month == month)
        is_in_range = (today <= day <= two_months_from_now)
        days_to_display.append({
            'day': day,
            'in_current_month': in_current_month,
            'is_in_range': is_in_range,
        })

    month_name = requested_date.strftime("%B %Y")

    # Prev/Next logic
    prev_year, prev_month = year, month - 1
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    next_year, next_month = year, month + 1
    if next_month > 12:
        next_month = 1
        next_year += 1

    can_go_previous = today.replace(year=prev_year, month=prev_month, day=1) >= today.replace(day=1)
    can_go_next = today.replace(year=next_year, month=next_month, day=1) <= two_months_from_now.replace(day=1)

    context = {
        'month_name': month_name,
        'year': year,
        'month': month,
        'days_to_display': days_to_display,
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'can_go_previous': can_go_previous,
        'can_go_next': can_go_next,
        'today': today,
    }
    return render(request, 'mobile/monthly_calendar.html', context)


# ------------------------------------------
# DAILY SCHEDULER
# ------------------------------------------
from django.utils.timezone import make_aware

@login_required
def daily_scheduler_view(request):
    """
    Displays a day-by-day schedule.
    - Members can multi-select available slots and instantly book them if they have enough credits.
    - Non-members see a link to the reservation form.
    - Shows the actual name of the user who booked the slot to other members,
      otherwise it just says "Booked."
    """
    today = localtime(now()).date()
    selected_date_str = request.GET.get('date', today.isoformat())
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    # Disallow booking in the past
    if selected_date < today:
        return redirect(f"/daily-scheduler/?date={today.isoformat()}")

    # Handle POST: user is trying to instantly book multiple hours
    if request.method == "POST" and request.POST.get("action") == "book_selected":
        if request.user.profile.has_minimum_role('member'):
            selected_hours_str = request.POST.get("selected_hours", "")
            if selected_hours_str:
                hours_list = [int(h) for h in selected_hours_str.split(",") if h.isdigit()]

                # Check membership
                try:
                    membership = request.user.usermembership
                except UserMembership.DoesNotExist:
                    membership = None

                if membership and membership.active and membership.credits >= len(hours_list):
                    # Book each selected hour
                    for hour in hours_list:
                        booked_start_time = datetime.strptime(f"{hour}:00", "%H:%M").time()
                        booked_datetime = datetime.combine(selected_date, booked_start_time)
                        booked_datetime_aware = make_aware(booked_datetime)

                        BookedSession.objects.create(
                            booked_by=request.user,
                            booked_date=selected_date,
                            booked_start_time=booked_start_time,
                            booked_datetime=booked_datetime_aware,  # Set the booked_datetime field
                            duration_hours=1,
                            status="booked"
                        )
                    # Subtract credits
                    membership.credits -= len(hours_list)
                    membership.save()

                    messages.success(request, f"You booked {len(hours_list)} hour(s) on {selected_date}!")
                else:
                    messages.error(request, "You do not have enough credits or your membership is not active.")
            else:
                messages.error(request, "No hours were selected.")
        else:
            messages.error(request, "Only members can book multiple sessions directly.")

        return redirect(f"/daily-scheduler/?date={selected_date.isoformat()}")

    # 1) Gather booked sessions for this date
    booked_sessions = BookedSession.objects.filter(
        booked_date=selected_date,
        status__in=["booked", "paid"]  # Include only these statuses
    )

    # We'll map hour -> (status, booked_by_name)
    booked_map = {}
    for session in booked_sessions:
        h = session.booked_start_time.hour
        # We'll store status="reserved" or "booked" (whatever label you want).
        # We'll capture the user name for display if viewer is a member.
        if session.booked_by:
            user_name = session.booked_by.get_full_name() or session.booked_by.username
        else:
            user_name = None
        booked_map[h] = {
            "status": "reserved",
            "booked_by_name": user_name
        }

    # 2) If you want to account for pending requests
    pending_requests = PendingSessionRequest.objects.filter(
        requested_date=selected_date,
        status__in=["pending", "approved", "paid"]
    )

    pending_map = {}
    for req in pending_requests:
        start_hour = req.requested_time.hour
        end_hour = start_hour + req.hours
        for h in range(start_hour, end_hour):
            if req.status == "approved":
                pending_map[h] = {
                    "status": "pending",
                    "booked_by_name": "Pending"
                }
            elif req.status == "paid":
                pending_map[h] = {
                    "status": "reserved",
                    "booked_by_name": "Paid"
                }
            else:  # "pending" or other
                pending_map[h] = {
                    "status": "requested",
                    "booked_by_name": "Requested"
                }

    # Build time slots (e.g. from 8:00 to 23:00 or from 'now' to 23:00)
    start_hour = localtime(now()).hour if selected_date == today else 8
    time_slots = []
    for hour in range(start_hour, 24):
        if hour in booked_map:
            info = booked_map[hour]
            time_slots.append({
                "hour": hour,
                "status": info["status"],
                # We'll store the raw name,
                # but decide how to show it in the template
                "booked_by_name": info["booked_by_name"]
            })
        elif hour in pending_map:
            info = pending_map[hour]
            time_slots.append({
                "hour": hour,
                "status": info["status"],
                "booked_by_name": info["booked_by_name"]
            })
        else:
            # available
            time_slots.append({
                "hour": hour,
                "status": "available",
                "booked_by_name": None
            })

    previous_date = (selected_date - timedelta(days=1)).isoformat()
    next_date = (selected_date + timedelta(days=1)).isoformat()
    can_go_previous = (selected_date > today)

    # Figure out if current viewer is a member & how many credits
    is_member = (request.user.profile.has_minimum_role('member'))
    user_credits = 0
    if is_member:
        try:
            user_credits = request.user.usermembership.credits
        except UserMembership.DoesNotExist:
            user_credits = 0

    context = {
        "selected_date": selected_date,
        "time_slots": time_slots,
        "previous_date": previous_date,
        "next_date": next_date,
        "can_go_previous": can_go_previous,
        "is_member": is_member,
        "max_credits": user_credits,
    }
    return render(request, "mobile/daily_scheduler.html", context)


# ------------------------------------------
# OPERATOR DASHBOARD
# ------------------------------------------
@login_required
@role_required("operator")
def operator_dashboard_view(request):
    """
    Shows pending session requests (status='pending').
    Operators can approve or reject.
    If approved, you could create BookedSession or send Payment Link, etc.
    """
    pending_requests = PendingSessionRequest.objects.filter(status='pending').order_by('-created_at')

    if request.method == "POST":
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        suggested_times = request.POST.get('suggested_times', "").strip()

        if request_id and action:
            try:
                pending_req = PendingSessionRequest.objects.get(id=request_id)

                if action == "accept":
                    pending_req.status = "approved"
                    pending_req.save()
                    send_payment_email_stripe(pending_req)
                    messages.success(request, "Request approved. Payment email sent.")
                elif action == "reject":
                    pending_req.status = "declined"
                    pending_req.save()
                    send_rejection_email(pending_req, suggested_times)
                    messages.success(request, "Request rejected and client notified.")

            except PendingSessionRequest.DoesNotExist:
                messages.error(request, "The request could not be found.")
            except Exception as e:
                print(f"Error processing the request: {e}")
                messages.error(request, "Error processing the request. Please try again.")

        return redirect('operator_dashboard')

    context = {'pending_requests': pending_requests}
    return render(request, 'mobile/operator_dashboard.html', context)


# ------------------------------------------
# STRIPE WEBHOOKS & PAYMENT SUCCESS
# ------------------------------------------
def payment_success(request):
    messages.success(request, "Your payment has been successfully completed!")
    return redirect("home")

# ------------------------------------------
# INVITES & REGISTRATION
# ------------------------------------------
def create_invite_view(request):
    """
    Allows staff to create an Invite for a new user (member/operator).
    """
    if request.method == 'POST':
        email = request.POST.get('email')
        role = request.POST.get('role')

        existing_invite = Invite.objects.filter(email=email).first()
        if existing_invite:
            # If it already exists but expired, refresh it
            if existing_invite.expires_at < now():
                existing_invite.token = get_random_string(length=64)
                existing_invite.role = role
                existing_invite.expires_at = now() + timedelta(days=7)
                existing_invite.is_used = False
                existing_invite.save()
                messages.success(request, f"Invite for {email} has been updated and resent.")
            else:
                messages.error(request, f"An active invite already exists for {email}.")
            return redirect('create_invite')

        # Create a fresh invite
        token = get_random_string(length=64)
        invite = Invite.objects.create(email=email, role=role, token=token)
        registration_link = f"{settings.BASE_URL}/register/{invite.token}/"

        email_subject = "You’re Invited to Join AVEC Studios"
        email_body = f"""
        <div style="font-family:Arial, sans-serif; font-size:16px; color:#333; line-height:1.5; margin:0 auto; max-width:600px; padding:20px;">
            <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">You’re Invited to Join AVEC Studios</h2>
            <p>Hi,</p>
            <p>You have been invited to join AVEC Studios as a {role}. Click below to complete your registration:</p>
            <div style="text-align:center; margin:30px 0;">
                <a href="{registration_link}"
                   style="background-color:#000; color:#fff; text-decoration:none; padding:15px 25px; border-radius:5px; font-size:18px; font-weight:bold;">
                    Register Now
                </a>
            </div>
            <p>This link expires on {invite.expires_at.strftime('%Y-%m-%d %H:%M:%S')}.</p>
            <p>If you didn’t expect this email, you can ignore it.</p>
            <p>Regards,<br>AVEC Studios Team</p>
        </div>
        """

        send_mail(
            subject=email_subject,
            message="You've been invited to join AVEC Studios. Use the link to register.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=email_body,
        )

        messages.success(request, f"Invite sent to {email}!")
        return redirect('create_invite')

    return render(request, 'admin/create_invite.html')


def register_view(request, token):
    """
    A user clicks an invite link to register.
    We validate the token, create a new User with the specified role.
    """
    invite = get_object_or_404(Invite, token=token)

    if not invite.is_valid():
        return render(request, "error.html", {"message": "Invalid or expired invite link."})

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = User.objects.create_user(username=username, email=invite.email, password=password)
        user.profile.role = invite.role
        user.save()

        invite.is_used = True
        invite.save()

        login(request, user)
        return redirect("home")

    return render(request, "mobile/register.html", {"invite": invite})


# ------------------------------------------
# ADMIN DASHBOARD (EXAMPLE)
# ------------------------------------------
from django.urls import reverse

@login_required
def admin_dashboard(request):
    """
    Admin dashboard with profile management, invite creation, and backend access.
    """
    # Restrict access to admin role
    if request.user.profile.role != "admin":
        return HttpResponseForbidden("You are not authorized to access this page.")

    # Handle POST request for profile updates
    if request.method == "POST":
        user_profile = request.user.profile
        user_profile.phone = request.POST.get("phone", user_profile.phone)
        user_profile.save()

        # Update Django's User model
        user = request.user
        user.first_name = request.POST.get("first_name", user.first_name)
        user.last_name = request.POST.get("last_name", user.last_name)
        user.email = request.POST.get("email", user.email)
        user.save()

        messages.success(request, "Your profile has been updated.")
        return redirect('admin_dashboard')

    # Check membership status
    try:
        membership = request.user.usermembership
        membership_status = "Paid" if membership.active else "Unpaid"
    except UserMembership.DoesNotExist:
        membership_status = "Unpaid"

    # Provide a URL for creating invites
    create_invite_url = reverse("create_invite")

    # Retrieve ADMIN_URL from the environment
    admin_url = settings.ADMIN_URL

    context = {
        'membership_status': membership_status,
        'create_invite_url': create_invite_url,
        'admin_url': admin_url,  # Pass admin URL to the template
    }
    return render(request, 'admin/dashboard.html', context)
