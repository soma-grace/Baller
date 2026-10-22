import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("baller.mailer")


def send_verification_email(to_email: str, name: str, code: str) -> bool:
    host = os.getenv("SMTP_HOST")
    if not host:
        # No SMTP configured: print the code so local development still works.
        logger.warning("SMTP not configured. Verification code for %s: %s", to_email, code)
        print(f"[Baller] Verification code for {to_email}: {code}")
        return True

    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "no-reply@baller.app"
    message = EmailMessage()
    message["Subject"] = "Your Baller verification code"
    message["From"] = sender
    message["To"] = to_email
    message.set_content(
        f"Hi {name},\n\n"
        f"Your Baller verification code is {code}.\n"
        "It expires in 15 minutes. If you didn't sign up, ignore this email.\n"
    )

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        with server:
            user = os.getenv("SMTP_USER")
            if user:
                server.login(user, os.getenv("SMTP_PASSWORD", ""))
            server.send_message(message)
        return True
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
        return False
