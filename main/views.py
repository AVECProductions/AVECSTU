# main/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.core.mail import EmailMessage
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.utils.timezone import localtime, now, timedelta, make_aware
from django.conf import settings
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from datetime import datetime
import calendar
import stripe

# Models & Forms
from .models import (
    PendingSessionRequest,
    BookedSession,
    Invite,
    UserMembership,
    UserProfile,
    MembershipPlan
)
from .forms import ProfileUpdateForm

# Services & Emails
from .services import (
    cancel_stripe_subscription,
    has_membership_access,
    create_stripe_customer
)
from .emails import (
    send_rejection_email,
    send_payment_email_stripe,
    send_cancelation_confirmation_email,
    send_invite_email,
    notify_operators_of_new_request
)

# Decorators
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
# HOME & AUTHENTICATION
# ------------------------------------------
def home_view(request):
    """
    Public home page (not password protected).
    Shows different dashboard options based on user roles.
    """
    user = request.user
    is_admin = False
    is_operator = False
    is_member = False

    if user.is_authenticated:
        profile = getattr(user, "profile", None)
        if profile:
            # Check for admin role
            is_admin = profile.has_minimum_role("admin")
            # Check for operator role
            is_operator = profile.has_minimum_role("operator")
            # Check for member role
            is_member = profile.has_minimum_role("member")

    context = {
        'is_logged_in': user.is_authenticated,
        'is_admin': is_admin,
        'is_operator': is_operator,
        'is_member': is_member,
        'current_time': now(),
    }
    return render(request, 'main/home.html', context)


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

    return render(request, 'credential/member_login.html', {'error': error})


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

    return render(request, "credential/guest_login.html", {"error": error})


@login_required
def member_logout_view(request):
    logout(request)
    return redirect('home')


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
        user_profile.phone = request.POST.get("phone", user_profile.user.phone)
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


from datetime import date

@login_required
def membership_management_view(request):
    """
    Allows members to view and manage their membership status.
    """
    try:
        membership = request.user.usermembership

        # Determine membership status and context values
        if membership.active:
            membership_status = "Active"
            valid_until_display = None  # Do not display "Valid Until" if membership is active
            next_billing_date = membership.next_billing_date
        else:
            membership_status = "Inactive"
            if membership.valid_until and membership.valid_until >= date.today():
                valid_until_display = membership.valid_until  # Show "Valid Until" if still in the future
            else:
                valid_until_display = None  # Do not display "Valid Until" if date is in the past
            next_billing_date = None  # No next billing date for inactive memberships

        context = {
            "membership_status": membership_status,
            "membership_plan": membership.plan.name if membership.plan else "No Plan",
            "credits": membership.credits,
            "next_billing_date": next_billing_date,
            "valid_until": valid_until_display,
        }
    except UserMembership.DoesNotExist:
        context = {
            "membership_status": "Inactive",
            "membership_plan": None,
            "credits": 0,
            "next_billing_date": None,
            "valid_until": None,
        }

    return render(request, "member/membership_management.html", context)




@login_required
def session_manager_view(request):
    """
    Allows members to manage their booked sessions.
    They can view and cancel their own bookings.
    """
    user = request.user
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
                booked_session.status = "canceled"
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
# Membership Payment Views
# ------------------------------------------
@login_required
def pay_january_rent(request):
    user = request.user
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        # Create a one-time payment Checkout Session
        checkout_session = stripe.checkout.Session.create(
            customer=user.profile.stripe_customer_id,
            payment_method_types=['card'],
            mode='payment',  # <-- KEY: one-time payment mode
            line_items=[{"price": "price_1QgdQ608vvVeCKwuUX6OgsUY", "quantity": 1}],
            metadata={
                'user_id': user.id,
                'plan_id': 1,  # So your webhook can see which plan
            },
            success_url=request.build_absolute_uri('/membership-management/'),
            cancel_url=request.build_absolute_uri('/membership-management/'),
        )

        return redirect(checkout_session.url, code=303)

    except MembershipPlan.DoesNotExist:
        messages.error(request, "Membership plan not found.")
        return redirect("membership_management")
    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        print(f"Error creating Stripe Checkout Session: {e}")
        return redirect("membership_management")

@login_required
def pay_membership(request):
    user = request.user
    stripe_product_id = 'prod_RZn1bb7U5b2DWc'  # Example product ID (from MembershipPlan)

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        # Retrieve the membership plan
        plan = MembershipPlan.objects.get(stripe_product_id=stripe_product_id)

        # Fetch active prices for the product from Stripe
        product_prices = stripe.Price.list(product=stripe_product_id, active=True)
        stripe_price_id = product_prices['data'][0]['id']  # Use the first active price

        # Calculate the timestamp for the first day of the next month
        today = localtime(now()).date()
        if today.month < 12:
            first_of_next_month = today.replace(month=today.month + 1, day=1)
        else:
            first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)

        # Convert to Unix timestamp using datetime.combine()
        billing_cycle_anchor = int(datetime.combine(first_of_next_month, datetime.min.time()).timestamp())

        # Create a Stripe Checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=user.profile.stripe_customer_id,  # Attach the Stripe customer ID
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{"price": stripe_price_id, "quantity": 1}],
            metadata={
                'user_id': user.id,
                'plan_id': plan.id,
            },
            subscription_data={
                'billing_cycle_anchor': billing_cycle_anchor,
                'proration_behavior': 'none',  # Prorate remaining days in the current month
            },
            success_url=request.build_absolute_uri('/membership-management/'),
            cancel_url=request.build_absolute_uri('/membership-management/'),
        )

        return redirect(checkout_session.url, code=303)
    except MembershipPlan.DoesNotExist:
        messages.error(request, "Membership plan not found.")
        return redirect("membership_management")
    except Exception as e:
        messages.error(request, f"An error occurred: {str(e)}")
        print(f"Error creating Stripe Checkout Session: {e}")
        return redirect("membership_management")

@login_required
def cancel_membership(request):
    """
    Cancels the user's membership and the associated Stripe subscription.
    """
    user = request.user
    try:
        membership = user.usermembership
        if membership.active and membership.stripe_subscription_id:
            # Cancel on Stripe
            success = cancel_stripe_subscription(user)
            if success:
                membership.active = False
                membership.stripe_subscription_id = None
                membership.save()
                # Email confirmation
                send_cancelation_confirmation_email(user)
                messages.success(request, "Your membership has been successfully canceled.")
            else:
                messages.error(request, "There was an issue canceling your membership. Please try again.")
        else:
            messages.error(request, "You do not have an active membership to cancel.")
    except UserMembership.DoesNotExist:
        messages.error(request, "You do not have a membership to cancel.")

    return redirect("membership_management")

@login_required
def customer_portal_view(request):
    try:
        portal_url = generate_customer_portal_link(request)
        return redirect(portal_url)
    except Exception as e:
        messages.error(request, "An error occurred. Please try again later.")
        return redirect("membership_management")

def generate_customer_portal_link(request):
    stripe.api_key = settings.STRIPE_SECRET_KEY
    portal_session = stripe.billing_portal.Session.create(
        customer=request.user.profile.stripe_customer_id,
        return_url=request.build_absolute_uri('/membership-management/'),  # Redirect after portal use
    )
    return portal_session.url



# ------------------------------------------
# RESERVATION FORM & CALENDAR
# ------------------------------------------
@login_required
def reservation_form_view(request):
    """
    Allows guests or members to submit a session request.
    Creates a PendingSessionRequest for operator approval.
    """
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        date = request.GET.get("date")
        time_ = request.GET.get("time")
        hours = request.POST.get("hours", 1)
        notes = request.POST.get("notes", "")

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

        # Notify operators
        operators = User.objects.filter(groups__name="Operator")
        operator_emails = [op.email for op in operators if op.email]

        if operator_emails:
            # Instead of building the email inline, call our new function
            notify_operators_of_new_request(
                name=name,
                email=email,
                phone=phone,
                date_str=date,       # pass the raw string or use requested_date.isoformat()
                time_str=time_,      # pass the raw time string
                hours=hours,
                notes=notes,
                operator_emails=operator_emails
            )

        messages.success(request, "Your reservation request has been submitted.")
        return redirect("home")

    return render(request, "main/reservation_form.html")


def monthly_calendar_view(request):
    """
    Shows a monthly calendar, limited to 2 months in the future.
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
    return render(request, 'main/monthly_calendar.html', context)


@login_required
def daily_scheduler_view(request):
    """
    Displays a day-by-day schedule:
      - Members can multi-select available slots and instantly book them
        if they have enough credits.
      - Non-members see a link to the reservation form.
    """
    today = localtime(now()).date()
    selected_date_str = request.GET.get('date', today.isoformat())
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()

    if selected_date < today:
        return redirect(f"/daily-scheduler/?date={today.isoformat()}")

    # Handle POST to instantly book multiple hours
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

                active_member = has_membership_access(request.user)
                if membership and active_member and membership.credits >= len(hours_list):
                    # Book each selected hour
                    for hour in hours_list:
                        booked_start_time = datetime.strptime(f"{hour}:00", "%H:%M").time()
                        booked_datetime = datetime.combine(selected_date, booked_start_time)
                        booked_datetime_aware = make_aware(booked_datetime)

                        BookedSession.objects.create(
                            booked_by=request.user,
                            booked_date=selected_date,
                            booked_start_time=booked_start_time,
                            booked_datetime=booked_datetime_aware,
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

    # Gather booked sessions
    booked_sessions = BookedSession.objects.filter(
        booked_date=selected_date,
        status__in=["booked", "paid"]
    )
    booked_map = {}
    for session in booked_sessions:
        h = session.booked_start_time.hour
        user_name = session.booked_by.get_full_name() or session.booked_by.username if session.booked_by else None
        booked_map[h] = {
            "status": "reserved",
            "booked_by_name": user_name
        }

    # Gather pending requests
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
                pending_map[h] = {"status": "pending", "booked_by_name": "Pending"}
            elif req.status == "paid":
                pending_map[h] = {"status": "reserved", "booked_by_name": "Paid"}
            else:
                pending_map[h] = {"status": "requested", "booked_by_name": "Requested"}

    start_hour = localtime(now()).hour if selected_date == today else 8
    time_slots = []
    for hour in range(start_hour, 24):
        if hour in booked_map:
            info = booked_map[hour]
            time_slots.append({
                "hour": hour,
                "status": info["status"],
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
            time_slots.append({
                "hour": hour,
                "status": "available",
                "booked_by_name": None
            })

    previous_date = (selected_date - timedelta(days=1)).isoformat()
    next_date = (selected_date + timedelta(days=1)).isoformat()
    can_go_previous = (selected_date > today)
    is_member = request.user.profile.has_minimum_role('member')
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
    return render(request, "main/daily_scheduler.html", context)


# ------------------------------------------
# OPERATOR DASHBOARD
# ------------------------------------------
@login_required
@role_required("operator")
def operator_dashboard_view(request):
    """
    Operator Dashboard: Provides access to the Operator Console and other operator tools.
    """
    return render(request, "operator/dashboard.html")

@login_required
@role_required("operator")
def operator_console_view(request):
    """
    Shows pending session requests. Operators can approve or reject.
    If approved, sends payment link; if rejected, sends rejection email.
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
                messages.error(request, "Request could not be found.")
            except Exception as e:
                print(f"Error processing request: {e}")
                messages.error(request, "Error processing the request. Please try again.")

        return redirect('operator_console')

    context = {'pending_requests': pending_requests}
    return render(request, 'operator/console.html', context)


# ------------------------------------------
# Payment Success
# ------------------------------------------
def payment_success(request):
    messages.success(request, "Your payment has been successfully completed!")
    return redirect("home")


# ------------------------------------------
# INVITES & REGISTRATION
# ------------------------------------------
@login_required
def create_invite_view(request):
    """
    Allows staff to create an Invite for a new user (member/operator).
    """
    from django.utils.crypto import get_random_string

    if request.user.profile.role != "admin":
        return HttpResponseForbidden("You are not authorized to access this page.")

    if request.method == 'POST':
        email = request.POST.get('email')
        role = request.POST.get('role')

        existing_invite = Invite.objects.filter(email=email).first()
        if existing_invite:
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

        # Create a new invite
        token = get_random_string(length=64)
        invite = Invite.objects.create(email=email, role=role, token=token)

        # Instead of building the email inline, call our new function
        send_invite_email(invite=invite, role=role)

        messages.success(request, f"Invite sent to {email}!")
        return redirect('create_invite')

    return render(request, 'credential/create_invite.html')

def register_view(request, token):
    """
    A user clicks an invite link to register.
    Validates token, creates new User with the specified role, sets up profile fields,
    and creates a Stripe customer.
    """
    invite = get_object_or_404(Invite, token=token)

    if not invite.is_valid():
        return render(request, "error.html", {"message": "Invalid or expired invite link."})

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")  # new
        first_name = request.POST.get("first_name")
        last_name = request.POST.get("last_name")
        phone = request.POST.get("phone")

        # 1) Check if passwords match
        if password != confirm_password:
            # Re-render the form with an error, keeping other fields filled in
            return render(
                request,
                "credential/register.html",
                {
                    "invite": invite,
                    "error": "Passwords do not match. Please try again.",
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": phone,
                },
            )

        # 3) Create the user if passwords match
        user = User.objects.create_user(
            username=username,
            email=invite.email,  # Use email from the invite
            password=password,
            first_name=first_name,
            last_name=last_name
        )

        # Assign invite role & phone
        user.profile.role = invite.role
        user.profile.phone = phone

        try:
            # Create a Stripe customer
            stripe_customer_id = create_stripe_customer(
                email=invite.email,
                first_name=first_name,
                last_name=last_name
            )
            user.profile.stripe_customer_id = stripe_customer_id
            user.profile.save()

        except Exception as e:
            # Handle errors and rollback user creation if needed
            print(f"Error creating Stripe customer: {e}")
            user.delete()  # Rollback user creation
            return render(
                request,
                "error.html",
                {"message": "Error creating Stripe customer. Please try again later."}
            )

        # Mark the invite as used
        invite.is_used = True
        invite.save()

        # Log the user in and redirect
        login(request, user)
        return redirect("home")

    return render(request, "credential/register.html", {"invite": invite})


# ------------------------------------------
# ADMIN DASHBOARD
# ------------------------------------------
@login_required
def admin_dashboard(request):
    """
    Admin dashboard for 'admin' role.
    """
    if request.user.profile.role != "admin":
        return HttpResponseForbidden("You are not authorized to access this page.")

    if request.method == "POST":
        user_profile = request.user.profile
        user_profile.phone = request.POST.get("phone", user_profile.phone)
        user_profile.save()

        user = request.user
        user.first_name = request.POST.get("first_name", user.first_name)
        user.last_name = request.POST.get("last_name", user.last_name)
        user.email = request.POST.get("email", user.email)
        user.save()

        messages.success(request, "Your profile has been updated.")
        return redirect('admin_dashboard')

    try:
        membership = request.user.usermembership
        membership_status = "Paid" if membership.active else "Unpaid"
    except UserMembership.DoesNotExist:
        membership_status = "Unpaid"

    admin_url = settings.ADMIN_URL
    create_invite_url = reverse("create_invite")

    context = {
        'membership_status': membership_status,
        'create_invite_url': create_invite_url,
        'admin_url': admin_url,
    }
    return render(request, 'admin/dashboard.html', context)
