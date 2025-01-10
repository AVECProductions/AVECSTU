from django.conf import settings
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import EmailMessage
import stripe
from django.utils.html import escape

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# ------------------------------------------
# STRIPE WEBHOOKS
# ------------------------------------------

@csrf_exempt
def stripe_webhook(request):
    """
    Receives Stripe Webhook events for subscription management.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    # Handle the event types
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)
    elif event['type'] == 'invoice.payment_failed':
        subscription_id = event['data']['object']['subscription']
        handle_failed_payment(subscription_id)

    return JsonResponse({'status': 'success'})

# ------------------------------------------
# PAYMENT HANDLERS
# ------------------------------------------

def handle_successful_payment(session):
    """
    Marks the user's membership as active upon successful subscription payment.
    """
    try:
        user_id = session['metadata']['user_id']
        user = User.objects.get(id=user_id)

        # Activate the user's membership
        from .models import UserMembership
        membership, created = UserMembership.objects.get_or_create(user=user)
        membership.active = True
        membership.stripe_subscription_id = session.get('subscription', None)  # Save subscription ID
        membership.save()

        # Optionally, send a confirmation email
        send_membership_confirmation_email(user)

    except KeyError:
        print("No 'user_id' in metadata.")
    except User.DoesNotExist:
        print(f"User with ID {user_id} not found.")


def handle_failed_payment(subscription_id):
    """
    Deactivates the membership when a payment fails.
    """
    try:
        from .models import UserMembership
        membership = UserMembership.objects.get(stripe_subscription_id=subscription_id)
        membership.active = False
        membership.save()

        # Optionally notify the user
        send_payment_failure_email(membership.user)

    except UserMembership.DoesNotExist:
        print(f"No membership found for subscription ID: {subscription_id}")

# ------------------------------------------
# EMAIL HANDLERS
# ------------------------------------------

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
            <p>Best regards,</p>
            <p>AVEC Studios Team</p>
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


def send_membership_confirmation_email(user):
    """
    Sends a confirmation email upon successful subscription.
    """
    try:
        email_content = f"""
        <div>
            <h2>Membership Activated</h2>
            <p>Hi {user.first_name},</p>
            <p>Your membership has been successfully activated. Thank you for subscribing!</p>
            <p>Best regards,<br>AVEC Studios</p>
        </div>
        """

        msg = EmailMessage(
            subject="Membership Confirmation",
            body=email_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.content_subtype = "html"
        msg.send()

    except Exception as e:
        print(f"Failed to send membership confirmation email: {e}")


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
            <p>Best regards,</p>
            <p>AVEC Studios Team</p>
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

# ------------------------------------------
# RESERVATION EMAILS
# ------------------------------------------

def send_payment_email_stripe(pending_req):
    """
    Example flow for sending a payment link to the user
    once the operator approves the request.
    """
    try:
        # Price example: $1 per entire request. (Adjust as needed.)
        amount = 1
        unit_amount = int(amount * 100)

        price = stripe.Price.create(
            unit_amount=unit_amount,
            currency="usd",
            product_data={"name": "Studio Booking Fee"},
        )

        payment_link = stripe.PaymentLink.create(
            line_items=[{"price": price.id, "quantity": 1}],
            payment_method_types=["card"],
            after_completion={
                "type": "redirect",
                "redirect": {"url": f"{settings.BASE_URL}/payment-success/"}
            },
            metadata={
                "reservation_id": pending_req.id  # used in webhook
            },
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
                <a href="{payment_link.url}"
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
    Send a rejection email with optional alternative times.
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
