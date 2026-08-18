import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def send_email(to_email, subject, body):
    try:
        message = Mail(
            from_email=os.environ.get('MAIL_DEFAULT_SENDER'),
            to_emails=to_email,
            subject=subject,
            plain_text_content=body
        )
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        sg.send(message)
        print(f">>> Email trimis la {to_email}")
        return True
    except Exception as e:
        print(f">>> Email error: {e}")
        return False