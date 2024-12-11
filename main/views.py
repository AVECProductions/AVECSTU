from django.shortcuts import render, redirect
from datetime import datetime, timedelta
from django.core.mail import send_mail
from django.contrib import messages
from django.conf import settings
from .models import ActiveRequest
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required

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
    for res in reservations:
        start_hour = res.requested_time.hour
        for h in range(start_hour, start_hour + res.hours):
            if res.status == "approved":
                reserved_hours[h] = res.name
            elif res.status == "pending":
                pending_hours[h] = "Pending"

    # Determine start hour for current date
    start_hour = today.hour if selected_date.date() == today.date() else 8  # 8 AM default for other dates

    # Prepare time slot data
    time_slots = []
    for hour in range(start_hour, 24):  # From start_hour to 11 PM
        time_slot_status = "available"
        booked_by = None

        # Check if this timeslot is reserved or pending
        if hour in reserved_hours:
            time_slot_status = "reserved"
            booked_by = reserved_hours[hour]
        elif hour in pending_hours:
            time_slot_status = "pending"
            booked_by = pending_hours[hour]

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

                    # Send email notification
                    send_mail(
                        subject="Your Reservation Request Has Been Approved",
                        message=(
                            f"Hello {active_request.name},\n\n"
                            f"Your reservation request for {active_request.requested_date} at {active_request.requested_time} "
                            f"has been approved. We look forward to seeing you!\n\n"
                            f"Thank you,\nAVEC Studios"
                        ),
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[client_email],
                    )
                    messages.success(request, "Request approved and client notified.")
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

