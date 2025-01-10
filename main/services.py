# main/services.py

import stripe
from django.conf import settings
from .models import UserMembership

def cancel_stripe_subscription(user):
    """
    Cancels the user's Stripe subscription on Stripe and updates membership status.
    Returns True if successful, False otherwise.
    """
    try:
        membership = UserMembership.objects.get(user=user)
        if membership.stripe_subscription_id:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            stripe.Subscription.delete(membership.stripe_subscription_id)

            membership.active = False
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

