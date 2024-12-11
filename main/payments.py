import paypalrestsdk
from django.conf import settings

# Configure PayPal
paypalrestsdk.configure({
    "mode": settings.PAYPAL_MODE,  # sandbox or live
    "client_id": settings.PAYPAL_CLIENT_ID,
    "client_secret": settings.PAYPAL_CLIENT_SECRET,
})

def create_paypal_payment_link(amount, description, return_url, cancel_url, invoice_number):
    """
    Create a PayPal payment link.
    """
    payment = paypalrestsdk.Payment({
        "intent": "sale",
        "payer": {
            "payment_method": "paypal"
        },
        "redirect_urls": {
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
        "transactions": [{
            "amount": {
                "total": f"{amount:.2f}",
                "currency": "USD"
            },
            "description": description,
            "invoice_number": str(invoice_number),  # Ensure it's passed as a string
        }]
    })

    if payment.create():
        # Return the approval URL for the payment
        for link in payment.links:
            if link.rel == "approval_url":
                return link.href
    else:
        print(payment.error)
        raise Exception("Error creating PayPal payment")


def capture_paypal_payment(payment_id, payer_id):
    """
    Capture an approved PayPal payment.
    """
    payment = paypalrestsdk.Payment.find(payment_id)

    if payment.execute({"payer_id": payer_id}):
        print("Payment executed successfully")
        return payment  # You can return the payment details for further processing
    else:
        print(payment.error)
        raise Exception("Error capturing PayPal payment")
