
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape

logger = logging.getLogger("baller.mailer")


def send_verification_email(to_email: str, name: str, code: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("EMAIL_FROM")

    if not all([smtp_username, smtp_password, sender]):
        logger.error("Gmail SMTP environment variables are missing.")
        return False

    safe_name = escape(name)
    safe_code = escape(code)

    message = EmailMessage()
    message["Subject"] = "Your Baller verification code"
    message["From"] = sender
    message["To"] = to_email

    message.set_content(
        f"Hi {name},\n\n"
        f"Your Baller verification code is {code}.\n"
        "It expires in 15 minutes. "
        "If you didn't sign up, you can ignore this email.\n\n"
        "The Baller Team"
    )

    message.add_alternative(
        f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto;">
            <h2>Welcome to Baller!</h2>
            <p>Hi {safe_name},</p>
            <p>Use this code to verify your email address:</p>
            <h1 style="letter-spacing: 8px;">{safe_code}</h1>
            <p>This code expires in 15 minutes.</p>
            <p>If you didn't sign up, you can ignore this email.</p>
            <p>The Baller Team</p>
        </div>
        """,
        subtype="html",
    )

    try:
        context = ssl.create_default_context()

        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.send_message(message)

        logger.info("Verification email sent successfully to %s", to_email)
        return True

    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
        return False
