# notifier.py
import smtplib
import ssl
from email.message import EmailMessage

EMAIL_ADDRESS = "ncomputerudr@gmail.com"
EMAIL_PASSWORD = "xbie bfuw bmhh sskh"  # Prefer env var in production

def send_email(subject, body, to_email="rapincomputerudr@gmail.com"):
    try:
        msg = EmailMessage()
        msg.set_content(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        print("✅ Email sent:", subject)
    except Exception as e:
        print("❌ Failed to send email:", e)
