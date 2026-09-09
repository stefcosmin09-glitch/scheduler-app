import resend
import os

resend.api_key = os.environ.get('RESEND_API_KEY')

def send_email(to_email, subject, body):
    try:
        params = {
            "from": "Scheduler App <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        email = resend.Emails.send(params)
        print(f">>> Email trimis: {email}")
        return True
    except Exception as e:
        print(f">>> Email error: {e}")
        return False