import resend
import os
import base64

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

def send_email_with_attachment(to_email, subject, body, pdf_b64, filename):
    try:
        params = {
            "from": "Scheduler App <onboarding@resend.dev>",
            "to": [to_email],
            "subject": subject,
            "text": body,
            "attachments": [
                {
                    "filename": filename,
                    "content": pdf_b64,
                }
            ]
        }
        email = resend.Emails.send(params)
        print(f">>> Email cu attachment trimis: {email}")
        return True
    except Exception as e:
        print(f">>> Email attachment error: {e}")
        return False