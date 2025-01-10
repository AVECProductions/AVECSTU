# main/payments.py

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
import stripe
from datetime import date

from .emails import (
    send_payment_failure_email,
    send_membership_confirmation_email,
)
from .models import UserMembership

stripe.api_key = settings.STRIPE_SECRET_KEY


@csrf_exempt
def stripe_webhook(request):
    """
    Receives Stripe Webhook events for subscription management and session reservations.
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

    # Handle specific event types
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']

        # Determine if this is a subscription or a single session
        if session.get('subscription'):
            # Handle subscription payment
            handle_successful_payment(session)
        elif session.get('metadata') and 'reservation_id' in session['metadata']:
            # Handle single session reservation
            handle_reservation_payment(session)
        else:
            # Log unrecognized session type for debugging
            print(f"Unrecognized session type: {session}")

    elif event['type'] == 'invoice.payment_failed':
        subscription_id = event['data']['object'].get('subscription')
        if subscription_id:
            handle_failed_payment(subscription_id)

    return JsonResponse({'status': 'success'})


def handle_successful_payment(session):
    """
    Marks the user's membership as active upon successful subscription payment.
    """
    try:
        user_id = session['metadata']['user_id']
        user = User.objects.get(id=user_id)

        membership, _ = UserMembership.objects.get_or_create(user=user)

        # Update membership details
        membership.active = True
        membership.stripe_subscription_id = session.get('subscription', None)

        # Update the next billing date and valid_until date
        subscription = stripe.Subscription.retrieve(membership.stripe_subscription_id)
        next_billing_unix = subscription['current_period_end']
        next_billing_date = date.fromtimestamp(next_billing_unix)
        membership.next_billing_date = next_billing_date
        membership.valid_until = next_billing_date
        membership.save()

        # Send confirmation email
        send_membership_confirmation_email(user)

    except KeyError:
        print("No 'user_id' in checkout.session.metadata.")
    except User.DoesNotExist:
        print(f"User with ID {session['metadata'].get('user_id')} not found.")
    except Exception as e:
        print(f"Error in handle_successful_payment: {e}")



def handle_failed_payment(subscription_id):
    """
    Deactivates the membership when a payment fails.
    """
    try:
        membership = UserMembership.objects.get(stripe_subscription_id=subscription_id)
        membership.active = False
        membership.save()

        send_payment_failure_email(membership.user)
    except UserMembership.DoesNotExist:
        print(f"No membership found for subscription ID: {subscription_id}")
    except Exception as e:
        print(f"Error in handle_failed_payment: {e}")

def handle_reservation_payment(session):
    """
    Marks a session reservation as paid.
    """
    try:
        reservation_id = session['metadata']['reservation_id']

        from .models import PendingSessionRequest
        reservation = PendingSessionRequest.objects.get(id=reservation_id)
        reservation.status = "paid"
        reservation.save()

        # Optionally, send a confirmation email
        from .emails import send_reservation_payment_confirmation_email
        send_reservation_payment_confirmation_email(reservation)

    except KeyError:
        print("No 'reservation_id' in checkout.session.metadata.")
    except PendingSessionRequest.DoesNotExist:
        print(f"Reservation with ID {session['metadata'].get('reservation_id')} not found.")
    except Exception as e:
        print(f"Error in handle_reservation_payment: {e}")
