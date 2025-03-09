# main/emails.py

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.html import escape
from django.contrib.auth.models import User
import stripe  # only if you need it here
from .models import UserMembership

def send_payment_failure_email(user):
    """
    Sends an email notification for payment failure.
    """
    try:
        email_content = f"""
        <div>
            <h2>Payment Failed</h2>
            <p>Hi {user.first_name},</p>
            <p>Unfortunately, your recent payment for your membership has failed.</p>
            <p>Please update your payment information to continue enjoying your membership benefits.</p>
            <p>Best regards,<br>AVEC Studios Team</p>
        </div>
        """
        msg = EmailMessage(
            subject="Payment Failed",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.content_subtype = "html"
        msg.send()
    except Exception as e:
        print(f"Failed to send payment failure email: {e}")


def send_membership_confirmation_email(user, reactivation=False):
    """
    Sends a confirmation email when a user's membership is activated or reactivated.
    """
    subject = "Welcome to AVEC Studios Membership!" if not reactivation else "Your AVEC Studios Membership has been reactivated!"
    
    if reactivation:
        message = f"""
        Hello {user.first_name},
        
        Your AVEC Studios membership has been successfully reactivated.
        
        Best regards,
        The AVEC Studios Team
        """
    else:
        message = f"""
        Hello {user.first_name},
        
        Your AVEC Studios membership has been successfully activated.
        
        Best regards,
        The AVEC Studios Team
        """
    
    email = EmailMessage(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )
    email.send()


def send_cancelation_confirmation_email(user):
    """
    Sends a confirmation email after the user cancels their membership.
    """
    try:
        email_content = f"""
        <div>
            <h2>Membership Canceled</h2>
            <p>Hi {user.first_name},</p>
            <p>Your membership has been successfully canceled. If you have any questions, feel free to contact us.</p>
            <p>Best regards,<br>AVEC Studios Team</p>
        </div>
        """
        msg = EmailMessage(
            subject="Membership Canceled",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.content_subtype = "html"
        msg.send()
    except Exception as e:
        print(f"Failed to send cancelation confirmation email: {e}")


def send_payment_email_stripe(pending_req):
    """
    Sends a Stripe Checkout session link to the user after operator approval.
    """
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        amount = 1.00  # Example $1
        unit_amount = int(amount * 100)

        # Create a Checkout Session for one-time payment
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",  # Use "payment" for one-time payments
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {"name": "Studio Booking Fee"},
                        "unit_amount": unit_amount,
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "reservation_id": pending_req.id,
            },
            success_url=f"{settings.BASE_URL}/payment-success/",
            cancel_url=f"{settings.BASE_URL}/payment-cancelled/",
        )

        email_content = f"""
        <div style="font-family: Arial, sans-serif; font-size:16px; color:#333; line-height:1.5; margin:0 auto; max-width:600px; padding:20px;">
            <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">Complete Your Studio Reservation</h2>
            <p>Hi {pending_req.requester_name},</p>
            <p>Thank you for reserving the studio! Below are your request details:</p>
            <ul style="list-style-type:none; padding:0;">
                <li><strong>Date:</strong> {pending_req.requested_date.strftime("%b %d, %Y")}</li>
                <li><strong>Time:</strong> {pending_req.requested_time.strftime("%I:%M %p")}</li>
                <li><strong>Hours:</strong> {pending_req.hours} hour(s)</li>
                <li><strong>Amount Due:</strong> ${amount:.2f}</li>
            </ul>
            <p style="margin-top:20px;">To confirm your reservation, please complete the payment by clicking below:</p>
            <div style="text-align:center; margin:30px 0;">
                <a href="{checkout_session.url}"
                   style="background-color:#000; color:#fff; text-decoration:none; padding:15px 25px; border-radius:5px; font-size:18px; font-weight:bold;">
                    Complete Payment
                </a>
            </div>
            <p>If you have any questions, feel free to reply to this email.</p>
            <p>Thank you,<br>AVEC Studios</p>
        </div>
        """

        msg = EmailMessage(
            subject="Complete Your Payment for Studio Reservation",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[pending_req.requester_email],
        )
        msg.content_subtype = "html"
        msg.send()

    except Exception as e:
        print(f"Failed to send Stripe payment email: {e}")
        raise

def send_rejection_email(pending_req, suggested_times):
    """
    Sends a rejection email with optional alternative times.
    """
    try:
        daily_scheduler_link = f"{settings.BASE_URL}/daily-scheduler/?date={pending_req.requested_date.isoformat()}"
        suggested_html = ""
        if suggested_times:
            escaped_times = escape(suggested_times).replace("\n", "<br>")
            suggested_html = f"""
            <p>The operator has suggested the following alternative times:</p>
            <ul><li>{escaped_times}</li></ul>
            """

        email_content = f"""
        <div style="font-family:Arial, sans-serif; font-size:16px; color:#333; line-height:1.5; margin:0 auto; max-width:600px; padding:20px;">
            <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">Reservation Request Declined</h2>
            <p>Hi {pending_req.requester_name},</p>
            <p>Unfortunately, your reservation request for:</p>
            <ul style="list-style-type:none; padding:0;">
                <li><strong>Date:</strong> {pending_req.requested_date.strftime("%b %d, %Y")}</li>
                <li><strong>Time:</strong> {pending_req.requested_time.strftime("%I:%M %p")}</li>
            </ul>
            <p>has been declined.</p>
            {suggested_html}
            <p>You can view and book other available slots here:</p>
            <div style="text-align:center; margin:30px 0;">
                <a href="{daily_scheduler_link}"
                   style="background-color:#000; color:#fff; text-decoration:none; padding:15px 25px; border-radius:5px; font-size:18px; font-weight:bold;">
                    View Available Times
                </a>
            </div>
            <p>If you have any questions, feel free to reply to this email.</p>
            <p>Thank you,<br>AVEC Studios</p>
        </div>
        """

        msg = EmailMessage(
            subject="Your Reservation Request Has Been Declined",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[pending_req.requester_email],
        )
        msg.content_subtype = "html"
        msg.send()

    except Exception as e:
        print(f"Failed to send rejection email: {e}")
        raise


def send_invite_email(invite, role):
    """
    Sends an invite email to 'invite.email' with a registration link,
    using EmailMessage for consistency.
    """
    registration_link = f"{settings.BASE_URL}/register/{invite.token}/"
    expires_str = invite.expires_at.strftime('%Y-%m-%d %H:%M:%S')

    email_subject = "You're Invited to Join AVEC Studios"
    email_body = f"""
    <div style="font-family:Arial, sans-serif; font-size:16px; color:#333; line-height:1.5; margin:0 auto; max-width:600px; padding:20px;">
        <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">You're Invited to Join AVEC Studios</h2>
        <p>Hi,</p>
        <p>You have been invited to join AVEC Studios as a {role}. Click below to complete your registration:</p>
        <div style="text-align:center; margin:30px 0;">
            <a href="{registration_link}"
               style="background-color:#000; color:#fff; text-decoration:none; padding:15px 25px; border-radius:5px; font-size:18px; font-weight:bold;">
                Register Now
            </a>
        </div>
        <p>This link expires on {expires_str}.</p>
        <p>If you didn't expect this email, you can ignore it.</p>
        <p>Regards,<br>AVEC Studios Team</p>
    </div>
    """

    # Use EmailMessage for consistency
    msg = EmailMessage(
        subject=email_subject,
        body=email_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[invite.email],
    )
    msg.content_subtype = "html"
    msg.send()


def notify_operators_of_new_request(name, email, phone, date_str, time_str, hours, notes, operator_emails):
    """
    Sends an email to all operators notifying them of a new reservation request.
    """
    email_content = f"""
    <div style="font-family: Arial, sans-serif; color: #333; line-height: 1.5; max-width: 600px; margin: auto;">
        <h2 style="color: #000;">New Reservation Request</h2>
        <p>A new reservation request has been submitted:</p>
        <ul style="padding-left: 20px; color: #555;">
            <li><strong>Name:</strong> {name}</li>
            <li><strong>Email:</strong> {email}</li>
            <li><strong>Phone:</strong> {phone}</li>
            <li><strong>Date:</strong> {date_str}</li>
            <li><strong>Time:</strong> {time_str}</li>
            <li><strong>Duration:</strong> {hours} hour(s)</li>
            <li><strong>Notes:</strong> {notes or 'No additional notes'}</li>
        </ul>
        <p>Click below to review this request in the Operator Dashboard:</p>
        <div style="text-align: center; margin: 20px 0;">
            <a href="{settings.BASE_URL}/operator-dashboard/"
               style="background-color: #007bff; color: #fff; text-decoration: none; 
                      padding: 10px 20px; border-radius: 5px; font-size: 16px;">
                View Operator Dashboard
            </a>
        </div>
        <p style="color: #777;">AVEC Studios</p>
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

def send_reservation_payment_confirmation_email(reservation):
    """
    Sends a confirmation email to the user and notifies operators upon successful payment for a session reservation.
    """
    try:
        # Email to the user
        user_email_content = f"""
        <div style="font-family: Arial, sans-serif; font-size:16px; color:#333; line-height:1.5; margin:0 auto; max-width:600px; padding:20px;">
            <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">Reservation Confirmed</h2>
            <p>Hi {reservation.requester_name},</p>
            <p>Your reservation has been successfully confirmed. Here are the details of your booking:</p>
            <ul style="list-style-type:none; padding:0;">
                <li><strong>Date:</strong> {reservation.requested_date.strftime("%b %d, %Y")}</li>
                <li><strong>Time:</strong> {reservation.requested_time.strftime("%I:%M %p")}</li>
                <li><strong>Hours:</strong> {reservation.hours} hour(s)</li>
            </ul>
            <p>If you have any questions or need assistance, feel free to contact us.</p>
            <p>Thank you,<br>AVEC Studios</p>
        </div>
        """

        user_msg = EmailMessage(
            subject="Reservation Confirmed",
            body=user_email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[reservation.requester_email],
        )
        user_msg.content_subtype = "html"
        user_msg.send()

        # Email to the operators
        operators = User.objects.filter(groups__name="Operator")
        operator_emails = [op.email for op in operators if op.email]

        operator_email_content = f"""
        <div style="font-family: Arial, sans-serif; color: #333; line-height: 1.5; max-width: 600px; margin: auto;">
            <h2 style="color: #000;">Reservation Confirmed</h2>
            <p>A new reservation has been successfully confirmed:</p>
            <ul style="padding-left: 20px; color: #555;">
                <li><strong>Name:</strong> {reservation.requester_name}</li>
                <li><strong>Email:</strong> {reservation.requester_email}</li>
                <li><strong>Date:</strong> {reservation.requested_date.strftime("%b %d, %Y")}</li>
                <li><strong>Time:</strong> {reservation.requested_time.strftime("%I:%M %p")}</li>
                <li><strong>Hours:</strong> {reservation.hours} hour(s)</li>
            </ul>
            <p>Click below to review this reservation in the Operator Dashboard:</p>
            <div style="text-align: center; margin: 20px 0;">
                <a href="{settings.BASE_URL}/operator-dashboard/"
                   style="background-color: #007bff; color: #fff; text-decoration: none; 
                          padding: 10px 20px; border-radius: 5px; font-size: 16px;">
                    View Operator Dashboard
                </a>
            </div>
            <p style="color: #777;">AVEC Studios</p>
        </div>
        """

        operator_msg = EmailMessage(
            subject="Reservation Confirmed",
            body=operator_email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=operator_emails,
        )
        operator_msg.content_subtype = "html"
        operator_msg.send()

    except Exception as e:
        print(f"Failed to send reservation confirmation email: {e}")

def send_recurring_payment_confirmation_email(user, credits, next_billing_date):
    """
    Sends an email confirmation for a successful recurring payment.
    """
    try:
        email_content = f"""
        <div style="font-family: Arial, sans-serif; font-size:16px; color:#333; line-height:1.5; margin:0 auto; max-width:600px; padding:20px;">
            <h2 style="font-size:24px; font-weight:bold; text-align:center; color:#333;">Membership Payment Successful</h2>
            <p>Hi {user.first_name},</p>
            <p>We have successfully processed your recurring membership payment. Here are the details:</p>
            <ul>
                <li><strong>Next Billing Date:</strong> {next_billing_date.strftime('%B %d, %Y')}</li>
                <li><strong>Updated Credits:</strong> {credits} hours</li>
            </ul>
            <p>Thank you for being a valued member of AVEC Studios!</p>
            <p>Best regards,<br>AVEC Studios Team</p>
        </div>
        """
        msg = EmailMessage(
            subject="Membership Payment Successful",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.content_subtype = "html"
        msg.send()
    except Exception as e:
        print(f"Failed to send recurring payment confirmation email: {e}")

def send_cancellation_scheduled_email(user, valid_until):
    """
    Sends an email notifying the user that their membership will be canceled at the end of the billing cycle.
    """
    subject = "Your Membership Cancellation is Scheduled"
    message = f"""
    Hi {user.first_name},

    Your membership cancellation has been scheduled. Your membership will remain active until {valid_until}.
    If you'd like to reactivate your membership before that date, you can do so through your membership portal.

    Thank you,
    The Team
    """
    user.email_user(subject, message)
