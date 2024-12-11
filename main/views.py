from django.shortcuts import render, redirect
from datetime import datetime, timedelta
from django.core.mail import send_mail
from django.contrib import messages
from django.conf import settings
from .models import ActiveRequest
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .payments import create_paypal_payment_link, capture_paypal_payment
from django.utils.html import format_html
from django.core.mail import EmailMessage
from django.utils.html import escape
from django.urls import reverse

# Predefined password for login
PREDEFINED_PASSWORD = "avec"

def login_view(request):
    error = None
    if request.method == "POST":
        password = request.POST.get("password")
        if password == PREDEFINED_PASSWORD:
            # Redirect to the Home Screen instead of the Scheduler
            return redirect('home')
        else:
            # If incorrect, set an error message
            error = "Invalid password. Please try again."

    # Render the login page with the error message (if any)
    return render(request, 'mobile/login.html', {'error': error})

def home_view(request):
    # Check if the user is authenticated
    is_logged_in = request.user.is_authenticated

    # Render the home screen with appropriate options
    return render(request, 'mobile/home.html', {'is_logged_in': is_logged_in})

def member_login_view(request):
    error = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')  # Redirect to Home Screen after login
        else:
            error = "Invalid credentials. Please try again."

    return render(request, 'mobile/member_login.html', {'error': error})

@login_required
def member_logout_view(request):
    logout(request)
    return redirect('home')  # Redirect to Home Screen after logout

def reservation_form_view(request):
    # Get date and time from query parameters
    date_str = request.GET.get('date', '')
    time_str = request.GET.get('time', '')

    # Parse the date and time strings into a datetime object
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        formatted_date = date_obj.strftime('%b %d, %Y')  # Format: Dec 5, 2024
    except ValueError:
        formatted_date = date_str  # Fallback if date parsing fails

    formatted_date_time = f"{formatted_date} at {time_str}"

    if request.method == "POST":
        # Collect form data
        name = request.POST.get("name")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        hours = request.POST.get("hours")
        notes = request.POST.get("notes")

        # Save the request to the database
        ActiveRequest.objects.create(
            name=name,
            email=email,
            phone=phone,
            requested_date=date_str,
            requested_time=time_str,
            hours=hours,
            notes=notes,
        )

        # Add success message
        messages.success(request, "Request Submitted Successfully.")

        # Redirect back to the scheduler page
        return redirect('week_scheduler')

    # Pass date and time to the template
    return render(request, 'mobile/reservation_form.html', {'formatted_date_time': formatted_date_time})


def week_scheduler_view(request):
    today = datetime.today()
    today_str = today.strftime('%Y-%m-%d')

    # Get the selected date from query parameters, default to today
    selected_date_str = request.GET.get('date', today_str)
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d')

    # If the selected date is before today, force it to today
    if selected_date.date() < today.date():
        return redirect(f"?date={today_str}")

    # Fetch all reservations (approved and pending) for the selected day
    reservations = ActiveRequest.objects.filter(
        requested_date=selected_date.date()
    )

    # Build dictionaries for reserved and pending slots
    reserved_hours = {}
    pending_hours = {}
    requested_hours = {}
    for res in reservations:
        start_hour = res.requested_time.hour
        for h in range(start_hour, start_hour + res.hours):
            if res.status == "paid":
                reserved_hours[h] = res.name
            elif res.status == "approved":
                # Instead of treating this as fully reserved, we could label it as "payment pending"
                pending_hours[h] = "Payment Pending"
            elif res.status == "pending":
                requested_hours[h] = "Requested"

    # Determine start hour for current date
    start_hour = today.hour if selected_date.date() == today.date() else 8  # 8 AM default for other dates

    # Prepare time slot data
    time_slots = []
    for hour in range(start_hour, 24):  # From start_hour to 11 PM
        time_slot_status = "available"
        booked_by = None

        if hour in reserved_hours:
            # paid
            time_slot_status = "reserved"
            booked_by = reserved_hours[hour]
        elif hour in pending_hours:
            # approved but not paid
            time_slot_status = "pending"
            booked_by = pending_hours[hour]
        elif hour in requested_hours:
            # requested but not approved
            # Create a new status called "requested" to differentiate it from others.
            time_slot_status = "requested"
            booked_by = requested_hours[hour]

        time_slots.append({
            "hour": hour,
            "status": time_slot_status,
            "booked_by": booked_by
        })

    # Navigation controls (previous/next date)
    previous_date = (selected_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_date = (selected_date + timedelta(days=1)).strftime('%Y-%m-%d')
    can_go_previous = selected_date.date() > today.date()

    context = {
        'selected_date': selected_date,
        'time_slots': time_slots,
        'previous_date': previous_date,
        'next_date': next_date,
        'can_go_previous': can_go_previous,
        'is_member': request.user.is_authenticated,  # Check if logged in
    }
    return render(request, 'mobile/week_scheduler.html', context)


def operator_dashboard_view(request):
    # Fetch all pending requests, sorted by newest created
    pending_requests = ActiveRequest.objects.filter(status='pending').order_by('-created_at')

    if request.method == "POST":
        # Handle accept/reject actions
        request_id = request.POST.get('request_id')
        action = request.POST.get('action')

        if request_id and action:
            try:
                active_request = ActiveRequest.objects.get(id=request_id)
                client_email = active_request.email

                # Update status
                if action == "accept":
                    active_request.status = "approved"
                    active_request.save()

                    # # Send email notification
                    # send_mail(
                    #     subject="Your Reservation Request Has Been Approved",
                    #     message=(
                    #         f"Hello {active_request.name},\n\n"
                    #         f"Your reservation request for {active_request.requested_date} at {active_request.requested_time} "
                    #         f"has been approved. We look forward to seeing you!\n\n"
                    #         f"Thank you,\nAVEC Studios"
                    #     ),
                    #     from_email=settings.DEFAULT_FROM_EMAIL,
                    #     recipient_list=[client_email],
                    # )
                    # messages.success(request, "Request approved and client notified.")
                    reservation = active_request
                    send_payment_email(reservation)
                elif action == "reject":
                    active_request.status = "declined"
                    active_request.save()

                    # Send email notification
                    send_mail(
                        subject="Your Reservation Request Has Been Declined",
                        message=(
                            f"Hello {active_request.name},\n\n"
                            f"Unfortunately, your reservation request for {active_request.requested_date} at {active_request.requested_time} "
                            f"has been declined. Please feel free to reach out to us for further assistance.\n\n"
                            f"Thank you,\nAVEC Studios"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[client_email],
                    )
                    messages.success(request, "Request rejected and client notified.")
            except ActiveRequest.DoesNotExist:
                messages.error(request, "The request could not be found.")
            except Exception as e:
                print(f"Error sending email: {e}")
                messages.error(request, "Error processing the request. Please try again.")

        # Redirect to avoid form resubmission
        return redirect('operator_dashboard')

    context = {'pending_requests': pending_requests}
    return render(request, 'mobile/operator_dashboard.html', context)

def send_payment_email(active_request):
    """
    Send a payment link to the user via email with improved formatting.
    """
    amount = active_request.hours * 50  # Example: $50 per hour
    description = f"Studio Reservation for {active_request.name} on {active_request.requested_date} at {active_request.requested_time}"
    return_url = f"http://127.0.0.1:8000/payment-return/"  # Replace with your actual domain
    cancel_url = f"http://127.0.0.1:8000/payment-cancelled/"  # Replace with your actual domain

    # Use ActiveRequest ID as the unique invoice number
    invoice_number = active_request.id

    try:
        payment_link = create_paypal_payment_link(amount, description, return_url, cancel_url, invoice_number)

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
                    <a href="{payment_link}"
                       style="background-color: #000000; color: #ffffff; text-decoration: none; padding: 15px 25px; border-radius: 5px; font-size:18px; font-weight:bold; display:inline-block;">
                        Complete Payment
                    </a>
                </div>
                <p>If you have any questions, feel free to reply to this email.</p>
                <p>Thank you,<br>AVEC Studios</p>
            </div>
        """

        # Send email
        email = EmailMessage(
            subject="Complete Your Payment for Studio Reservation",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[active_request.email],
        )
        email.content_subtype = "html"
        email.send()
    except Exception as e:
        print(f"Failed to create payment link: {e}")
        raise Exception("Failed to send payment email")



def paypal_return_view(request):
    payment_id = request.GET.get("paymentId")
    payer_id = request.GET.get("PayerID")

    if not payment_id or not payer_id:
        messages.error(request, "Payment was cancelled or failed.")
        return redirect("home")

    try:
        payment = capture_paypal_payment(payment_id, payer_id)

        # Extract the invoice number from the payment
        invoice_number = payment.transactions[0].invoice_number

        # Fetch the ActiveRequest using the invoice number
        active_request = ActiveRequest.objects.get(id=invoice_number)

        # Update the status to "paid"
        active_request.status = "paid"
        active_request.save()

        # Add a success message
        messages.success(request, "Your payment was successful and your booking is now confirmed!")

        # Redirect to the scheduler, passing the requested date as a query parameter
        date_str = active_request.requested_date.strftime('%Y-%m-%d')
        time_str = active_request.requested_time.strftime('%H:%M')
        return redirect(f"{reverse('week_scheduler')}?date={date_str}&time={time_str}")

    except Exception as e:
        print(f"Error capturing payment: {e}")
        messages.error(request, "Payment failed.")
        return redirect("home")


def payment_cancelled_view(request):
    """
    Handle the case when a user cancels payment.
    """
    messages.error(request, "Payment was cancelled.")
    return redirect("home")


