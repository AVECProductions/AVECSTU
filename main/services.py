# main/services.py

import stripe
from django.conf import settings
from .models import UserMembership
from datetime import date

stripe.api_key = settings.STRIPE_SECRET_KEY

def has_membership_access(user):
    """
    Determines if a user has valid membership access.
    """
    try:
        membership = user.usermembership
        if membership.active:
            return True
        elif membership.valid_until and membership.valid_until >= date.today():
            return True
        return False
    except UserMembership.DoesNotExist:
        return False

def cancel_stripe_subscription(user):
    """
    Cancels the user's Stripe subscription on Stripe and updates membership validity.
    Returns True if successful, False otherwise.
    """
    try:
        membership = UserMembership.objects.get(user=user)
        if membership.stripe_subscription_id:
            stripe.Subscription.delete(membership.stripe_subscription_id)

            # Set valid_until and clear subscription info
            membership.valid_until = membership.next_billing_date
            membership.stripe_subscription_id = None
            membership.save()
            return True
        else:
            return False
    except UserMembership.DoesNotExist:
        print(f"Membership does not exist for user {user.username}.")
        return False
    except stripe.error.StripeError as e:
        print(f"Stripe error during subscription cancellation: {e}")
        return False


def create_stripe_customer(email, first_name, last_name):
    """
    Creates a Stripe customer and returns the customer ID.
    """
    try:
        stripe_customer = stripe.Customer.create(
            email=email,
            name=f"{first_name} {last_name}"
        )
        return stripe_customer['id']
    except stripe.error.StripeError as e:
        print(f"Stripe error: {e}")
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise e