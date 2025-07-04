# utils/email.py

import os
import requests

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = "noreply@zidepeople.com"  # Change this to your actual sender

def send_event_update_email(name, recipient_email, event_name):
    subject = f"Update on Event: {event_name}"
    content = f"""
    Hi {name},

    There has been an update to the event: {event_name}.
    Please check your dashboard or contact the organizer for more details.

    Best,
    ZidePeople Team
    """

    data = {
        "personalizations": [{
            "to": [{"email": recipient_email}],
            "subject": subject
        }],
        "from": {"email": SENDER_EMAIL},
        "content": [{
            "type": "text/plain",
            "value": content
        }]
    }

    response = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json"
        },
        json=data
    )

    if response.status_code not in [200, 202]:
        print("❌ Failed to send email:", response.text)
    else:
        print(f"✅ Email sent to {recipient_email}")





def send_collaborator_invite_email(to_email: str, event_id: int):
    """
    Placeholder: Sends an email inviting a user to collaborate on an event.
    This will be replaced with SendGrid or any other email service later.
    """
    print(f"📧 Sending collaboration invite to {to_email} for event ID {event_id}")
    # Later, generate a link like:
    # f"https://your-frontend.com/collaborator/respond?event_id={event_id}"
    # And send via SendGrid
