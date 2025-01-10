# main/payments.py

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
import stripe

from .emails import (
    send_payment_failure_email,
    send_membership_confirmation_email,
)
from .models import UserMembership

stripe.api_key = settings.STRIPE_SECRET_KEY


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

    # Handle specific event types
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        handle_successful_payment(session)
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
        membership.active = True
        membership.stripe_subscription_id = session.get('subscription', None)
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
