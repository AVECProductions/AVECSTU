from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from .models import ActiveRequest
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.utils.html import format_html
from django.core.mail import EmailMessage
from django.urls import reverse
import stripe
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import calendar
from datetime import datetime, date, timedelta
from django.utils.timezone import localtime, now, timedelta
from django.utils.html import escape

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

BASE_URL = settings.DOMAIN  # e.g., "https://yourdomain.com"


def home_view(request):
    """
    Public home page (not password protected).
    We removed the Stripe test button from here.
    """
    context = {
        'is_logged_in': request.user.is_authenticated,
        'current_time': now(),
    }
    is_logged_in = request.user.is_authenticated
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

        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            error = "Invalid credentials. Please try again."

    return render(request, 'mobile/member_login.html', {'error': error})
def guest_login_view(request):
    """
    Allow guests to log in using a shared password.
    """
    error = None  # Initialize error as None
    if request.method == "POST":
        guest_password = request.POST.get("password")

        # Log the user in as "public"
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


@login_required
def reservation_form_view(request):
    """
    Handle session booking for members and reservation requests for guests.
    """
    user = request.user

    # Guests can submit reservation requests
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        date = request.GET.get("date")
        time = request.GET.get("time")
        hours = request.POST.get("hours")
        notes = request.POST.get("notes")

        print(f"Date received from form: {date}")

        # Save the reservation request
        new_request = ActiveRequest.objects.create(
            name=name,
            email=email,
            phone=phone,
            requested_date=date,
            requested_time=time,
            hours=hours,
            notes=notes,
            status="pending",
        )

        # Notify all operators via email
        operators = User.objects.filter(groups__name="Operator")  # Assuming you have a group named "Operator"
        operator_emails = [operator.email for operator in operators if operator.email]

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
                    <li><strong>Time:</strong> {time}</li>
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

            email = EmailMessage(
                subject="New Reservation Request Submitted",
                body=email_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=operator_emails,
            )
            email.content_subtype = "html"  # Set the email content to HTML
            email.send()

        messages.success(request, "Your reservation request has been submitted.")
        return redirect("home")

    return render(request, "mobile/reservation_form.html")


def monthly_calendar_view(request):
    """
    Displays a monthly calendar (grid) with a dark theme, allowing
    users to pick a day and jump to the weekly scheduler.
    We limit to 2 months (approx 60 days) into the future.
    """
    today = localtime(now()).date()  # Current date in the local timezone
    two_months_from_now = today + timedelta(days=60)

    # Read year/month from GET params, default to today's year/month
    year = request.GET.get("year")
    month = request.GET.get("month")

    if year and month:
        try:
            year = int(year)
            month = int(month)
        except ValueError:
            # If invalid, reset to current month
            year = today.year
            month = today.month
    else:
        year = today.year
        month = today.month

    # Make sure we don't go below today's year/month
    # Or above two_months_from_now's year/month
    # We'll build a date for the 1st of that month, then compare
    requested_date = today.replace(year=year, month=month, day=1)
    if requested_date < today.replace(day=1):
        # If they are asking for a month in the past, redirect to the current month
        return redirect('monthly_calendar', permanent=False)
    elif requested_date > two_months_from_now.replace(day=1):
        # If they asked for beyond 2 months, redirect to 2 months from now
        return redirect(f'/monthly-calendar/?year={two_months_from_now.year}&month={two_months_from_now.month}')

    # Use Python's calendar to figure out how the month is laid out
    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.itermonthdates(year, month)

    # Build a list of all days (datetime.date) in this month
    days_to_display = []
    for day in month_days:
        in_current_month = (day.month == month)
        is_in_range = (day >= today) and (day <= two_months_from_now)
        days_to_display.append({
            'day': day,
            'in_current_month': in_current_month,
            'is_in_range': is_in_range,
        })

    # Figure out the month name (e.g., "December 2024")
    month_name = requested_date.strftime("%B %Y")

    # Compute previous/next month links
    prev_year, prev_month = year, month - 1
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1

    next_year, next_month = year, month + 1
    if next_month > 12:
        next_month = 1
        next_year += 1

    # Check if previous/next is valid in your 2-month range
    can_go_previous = today.replace(year=prev_year, month=prev_month, day=1) >= today.replace(day=1)
    can_go_next = today.replace(year=next_year, month=next_month, day=1) <= two_months_from_now.replace(day=1)

    context = {
        'month_name': month_name,  # e.g., "December 2024"
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


def daily_scheduler_view(request):
    """
    Only logged-in users can view/book slots on this scheduler.
    """
    today = localtime(now()).date()  # Get today's date in the current timezone

    # Default to today unless a date is passed in
    selected_date_str = request.GET.get('date', today.isoformat())  # Get ISO format string for the date
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()  # Convert to datetime.date

    # Force date to not be in the past
    if selected_date < today:  # Compare `datetime.date` objects
        return redirect(f"?date={today.isoformat()}")

    reservations = ActiveRequest.objects.filter(
        requested_date=selected_date  # Compare against `datetime.date`
    )

    reserved_hours = {}
    pending_hours = {}
    requested_hours = {}

    for res in reservations:
        start_hour = res.requested_time.hour
        for h in range(start_hour, start_hour + res.hours):
            if res.status == "paid":
                reserved_hours[h] = res.name
            elif res.status == "approved":
                pending_hours[h] = "Pending"
            elif res.status == "pending":
                requested_hours[h] = "Requested"

    start_hour = localtime(now()).hour if selected_date == today else 8

    time_slots = []
    for hour in range(start_hour, 24):
        time_slot_status = "available"
        booked_by = None

        if hour in reserved_hours:
            time_slot_status = "reserved"
            booked_by = reserved_hours[hour]
        elif hour in pending_hours:
            time_slot_status = "pending"
            booked_by = pending_hours[hour]
        elif hour in requested_hours:
            time_slot_status = "requested"
            booked_by = requested_hours[hour]

        time_slots.append({
            "hour": hour,
            "status": time_slot_status,
            "booked_by": booked_by
        })

    previous_date = (selected_date - timedelta(days=1)).isoformat()
    next_date = (selected_date + timedelta(days=1)).isoformat()
    can_go_previous = selected_date > today

    context = {
        'selected_date': selected_date,
        'time_slots': time_slots,
        'previous_date': previous_date,
        'next_date': next_date,
        'can_go_previous': can_go_previous,
        'is_member': request.user.is_authenticated,
    }
    return render(request, 'mobile/daily_scheduler.html', context)


@login_required
def operator_dashboard_view(request):
    """
    View for the operator/admin to review pending requests and approve or reject them.
    """
    pending_requests = ActiveRequest.objects.filter(status='pending').order_by('-created_at')

    if request.method == "POST":
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')
        suggested_times = request.POST.get('suggested_times', "").strip()  # Get suggested times

        if request_id and action:
            try:
                active_request = ActiveRequest.objects.get(id=request_id)
                client_email = active_request.email

                if action == "accept":
                    active_request.status = "approved"
                    active_request.save()
                    send_payment_email_stripe(active_request)
                    messages.success(request, "Request approved. Payment email sent.")
                elif action == "reject":
                    active_request.status = "declined"
                    active_request.save()
                    send_rejection_email(active_request, suggested_times)
                    messages.success(request, "Request rejected and client notified.")
            except ActiveRequest.DoesNotExist:
                messages.error(request, "The request could not be found.")
            except Exception as e:
                print(f"Error processing the request: {e}")
                messages.error(request, "Error processing the request. Please try again.")

        return redirect('operator_dashboard')

    context = {'pending_requests': pending_requests}
    return render(request, 'mobile/operator_dashboard.html', context)


def send_payment_email_stripe(active_request):
    """
    Generate a Stripe Payment Link and email it to the client.
    """
    try:
        # Price calculation example: $50 per hour
        #amount = active_request.hours * 50.0
        amount = 1
        # Stripe amounts are in cents
        unit_amount = int(amount * 100)

        # Create a Price dynamically (this will create a new ephemeral product for each request)
        price = stripe.Price.create(
            unit_amount=unit_amount,
            currency="usd",
            product_data={"name": "Studio Booking Fee"},

        )

        # Create the Payment Link
        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            payment_method_types=["card"],  # Allow card payments (includes Apple Pay)
            after_completion={
                "type": "redirect",
                "redirect": {"url": f"{settings.BASE_URL}/payment-success/"}
            },
            metadata={
                "reservation_id": active_request.id  # Embed the unique reservation ID
            },
        )

        email_content = f"""
        <div style="font-family: Arial, sans-serif; font-size:16px; color:#333333; line-height:1.5; margin: 0 auto; max-width:600px; padding:20px;">
            <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">Complete Your Studio Reservation</h2>
            <p>Hi {active_request.name},</p>
            <p>Thank you for reserving the studio! Below are your reservation details:</p>
            <ul style="list-style-type:none; padding:0;">
                <li><strong>Date:</strong> {active_request.requested_date.strftime("%b %d, %Y")}</li>
                <li><strong>Time:</strong> {active_request.requested_time.strftime("%I:%M %p")}</li>
                <li><strong>Hours:</strong> {active_request.hours} hour(s)</li>
                <li><strong>Amount Due:</strong> ${amount:.2f}</li>
            </ul>
            <p style="margin-top:20px;">To confirm your reservation, please complete the payment by clicking the button below:</p>
            <div style="text-align:center; margin: 30px 0;">
                <a href="{payment_link.url}"
                   style="background-color: #000000; color: #ffffff; text-decoration: none; padding: 15px 25px; border-radius: 5px; font-size:18px; font-weight:bold; display:inline-block;">
                    Complete Payment
                </a>
            </div>
            <p>If you have any questions, feel free to reply to this email.</p>
            <p>Thank you,<br>AVEC Studios</p>
        </div>
        """

        email = EmailMessage(
            subject="Complete Your Payment for Studio Reservation",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[active_request.email],
        )
        email.content_subtype = "html"
        email.send()

    except Exception as e:
        print(f"Failed to send Stripe payment email: {e}")
        raise

def send_rejection_email(active_request, suggested_times):
    """
    Send a rejection email with optional alternative times and a link to the daily scheduler.
    """
    try:
        daily_scheduler_link = f"{settings.BASE_URL}/daily-scheduler/?date={active_request.requested_date.strftime('%Y-%m-%d')}"
        suggested_times_message = ""

        # Add suggested times if provided
        if suggested_times:
            suggested_times_list = escape(suggested_times).replace("\n", "<br>")  # Escape and format
            suggested_times_message = f"""
                <p>The operator has suggested the following alternative times:</p>
                <ul>
                    <li>{suggested_times_list}</li>
                </ul>
            """

        email_content = f"""
        <div style="font-family: Arial, sans-serif; font-size:16px; color:#333333; line-height:1.5; margin: 0 auto; max-width:600px; padding:20px;">
            <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">Reservation Request Declined</h2>
            <p>Hi {active_request.name},</p>
            <p>Unfortunately, your reservation request for:</p>
            <ul style="list-style-type:none; padding:0;">
                <li><strong>Date:</strong> {active_request.requested_date.strftime("%b %d, %Y")}</li>
                <li><strong>Time:</strong> {active_request.requested_time.strftime("%I:%M %p")}</li>
            </ul>
            <p>has been declined.</p>
            {suggested_times_message}
            <p>You can view and book other available slots by visiting the link below:</p>
            <div style="text-align:center; margin: 30px 0;">
                <a href="{daily_scheduler_link}"
                   style="background-color: #000000; color: #ffffff; text-decoration: none; padding: 15px 25px; border-radius: 5px; font-size:18px; font-weight:bold; display:inline-block;">
                    View Available Times
                </a>
            </div>
            <p>If you have any questions, feel free to reply to this email.</p>
            <p>Thank you,<br>AVEC Studios</p>
        </div>
        """

        email = EmailMessage(
            subject="Your Reservation Request Has Been Declined",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[active_request.email],
        )
        email.content_subtype = "html"
        email.send()

    except Exception as e:
        print(f"Failed to send rejection email: {e}")
        raise


def payment_success(request):
    """
    Redirects to the home page with a success message after payment completion.
    """
    messages.success(request, "Your payment has been successfully completed!")
    return redirect("home")

@csrf_exempt
def stripe_webhook(request):
    print("webhook recieved")
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        # Update the reservation status to "paid"
        handle_successful_payment(session)

    return JsonResponse({'status': 'success'})

def handle_successful_payment(session):
    try:
        # Retrieve the reservation ID from the session metadata
        reservation_id = session['metadata']['reservation_id']
        reservation = ActiveRequest.objects.get(id=reservation_id)
        reservation.status = "paid"
        reservation.save()

        # Notify admin or send a confirmation email
        send_payment_confirmation_email(reservation)

    except KeyError:
        print("Metadata missing in the session.")
    except ActiveRequest.DoesNotExist:
        print(f"Reservation with ID {reservation_id} not found.")

def send_payment_confirmation_email(reservation):
    try:
        email_content = f"""
        <div>
            <h2>Payment Successful</h2>
            <p>Reservation Details:</p>
            <ul>
                <li>Name: {reservation.name}</li>
                <li>Date: {reservation.requested_date}</li>
                <li>Time: {reservation.requested_time}</li>
                <li>Hours: {reservation.hours}</li>
            </ul>
            <p>Thank you for your payment!</p>
        </div>
        """
        email = EmailMessage(
            subject="Payment Confirmation",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reservation.email],
        )
        email.content_subtype = "html"
        email.send()

    except Exception as e:
        print(f"Failed to send payment confirmation email: {e}")

