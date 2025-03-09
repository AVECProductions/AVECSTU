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
    send_recurring_payment_confirmation_email,
    send_cancelation_confirmation_email,
    send_cancellation_scheduled_email,
)
from .models import UserMembership, MembershipPlan

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
            print("initial payment")
            # Handle subscription payment
            handle_successful_payment(session)
        elif session.get('metadata') and 'reservation_id' in session['metadata']:
            # Handle single session reservation
            handle_reservation_payment(session)
        else:
            # Log unrecognized session type for debugging
            print(f"Unrecognized session type: {session}")

    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        subscription_id = invoice.get('subscription')
        # Distinguish between initial and recurring payments
        if subscription_id:
            if 'metadata' in invoice and 'user_id' in invoice['metadata']:
                pass
            else:
                # Handle recurring payments (no metadata)
                print("Processing recurring subscription payment")
                handle_recurring_payment(subscription_id)

    elif event['type'] == 'invoice.payment_failed':
        subscription_id = event['data']['object'].get('subscription')
        if subscription_id:
            handle_failed_payment(subscription_id)

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        handle_subscription_cancellation(subscription)

    if event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        handle_subscription_update(subscription)


    return JsonResponse({'status': 'success'})


def handle_successful_payment(session):
    """
    Marks the user's membership as active upon successful subscription payment.
    """
    print("successful payment!")
    try:
        user_id = session['metadata']['user_id']
        plan_id = session['metadata']['plan_id']  # Retrieve the plan ID from metadata
        user = User.objects.get(id=user_id)
        plan = MembershipPlan.objects.get(id=plan_id)  # Get the membership plan

        # Get or create the user's membership
        membership, created = UserMembership.objects.get_or_create(user=user)
        
        # Check if this is a reactivation
        reactivation = not created and not membership.active
        
        # Update membership details
        membership.active = True
        membership.plan = plan  # Assign the membership plan
        membership.stripe_subscription_id = session.get('subscription', None)

        # Retrieve subscription details from Stripe
        subscription = stripe.Subscription.retrieve(membership.stripe_subscription_id)
        next_billing_unix = subscription['current_period_end']
        next_billing_date = date.fromtimestamp(next_billing_unix)

        # Set billing dates and default credits
        membership.next_billing_date = next_billing_date
        membership.valid_until = next_billing_date
        
        # Assign credits if new or reactivating with zero credits
        if created or membership.credits == 0:
            membership.credits = 100
            
        membership.save()

        # Send confirmation email
        if reactivation:
            # You could create a specific reactivation email
            send_membership_confirmation_email(user, reactivation=True)
        else:
            send_membership_confirmation_email(user)

    except KeyError:
        print("No 'user_id' or 'plan_id' in checkout.session.metadata.")
    except User.DoesNotExist:
        print(f"User with ID {session['metadata'].get('user_id')} not found.")
    except MembershipPlan.DoesNotExist:
        print(f"Membership plan with ID {session['metadata'].get('plan_id')} not found.")
    except Exception as e:
        print(f"Error in handle_successful_payment: {e}")

def handle_recurring_payment(subscription_id):
    """
    Handles recurring subscription payments by updating membership details.
    """
    print("recurring payment!")
    try:
        # Find the membership associated with this subscription
        membership = UserMembership.objects.get(stripe_subscription_id=subscription_id)

        # Retrieve the subscription from Stripe
        subscription = stripe.Subscription.retrieve(subscription_id)

        # Verify the subscription status
        if subscription['status'] != 'active':
            print(f"Subscription {subscription_id} is not active.")
            return

        # Calculate the next billing date
        next_billing_unix = subscription['current_period_end']
        next_billing_date = date.fromtimestamp(next_billing_unix)

        # Update membership details
        membership.next_billing_date = next_billing_date
        membership.valid_until = next_billing_date
        
        # Check if membership was inactive and reactivate it
        was_inactive = not membership.active
        if was_inactive:
            print(f"Reactivating previously inactive membership for user {membership.user.username}")
            membership.active = True
            # You might want to send a special reactivation email here

        # Add recurring credits
        membership.credits += 100  # Add 100 credits each billing cycle
        membership.save()

        # Send notification email
        if was_inactive:
            # Send reactivation email
            send_membership_confirmation_email(membership.user)  # Or create a specific reactivation email
        else:
            # Send regular recurring payment email
            send_recurring_payment_confirmation_email(membership.user, membership.credits, next_billing_date)

        print(f"Recurring payment processed for user {membership.user.username}")

    except UserMembership.DoesNotExist:
        print(f"No membership found for subscription ID: {subscription_id}")
    except Exception as e:
        print(f"Error in handle_recurring_payment: {e}")


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


def handle_subscription_cancellation(subscription):
    """
    Handles cancellation of a Stripe subscription.
    """
    try:
        # Find the associated membership
        membership = UserMembership.objects.get(stripe_subscription_id=subscription['id'])
        membership.active = False  # Deactivate the membership
        membership.valid_until = None  # Clear the valid_until date
        membership.save()

        # Optional: Notify the user about the cancellation
        send_cancelation_confirmation_email(membership.user)

        print(f"Membership for user {membership.user.username} has been canceled.")
    except UserMembership.DoesNotExist:
        print(f"No membership found for subscription ID: {subscription['id']}")
    except Exception as e:
        print(f"Error handling subscription cancellation: {e}")


def handle_subscription_update(subscription):
    """
    Handles updates to a Stripe subscription, including end-of-cycle cancellations.
    """
    try:
        membership = UserMembership.objects.get(stripe_subscription_id=subscription['id'])

        # Check if cancellation is scheduled
        if subscription['cancel_at_period_end']:
            # Handle scheduled cancellation
            membership.active = False  # Membership is still active until the end of the cycle
            membership.valid_until = date.fromtimestamp(subscription['current_period_end'])
            membership.save()

            # Notify the user
            send_cancellation_scheduled_email(membership.user, membership.valid_until)

            print(f"Scheduled cancellation for user {membership.user.username}. Membership valid until {membership.valid_until}.")
        else:
            # Handle other updates (e.g., billing info changes)
            print(f"Subscription for user {membership.user.username} updated without cancellation.")

    except UserMembership.DoesNotExist:
        print(f"No membership found for subscription ID: {subscription['id']}")
    except Exception as e:
        print(f"Error handling subscription update: {e}")

