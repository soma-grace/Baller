
import logging
import os
import resend

logger = logging.getLogger("baller.mailer")


def send_verification_email(to_email: str, name: str, code: str) -> bool:
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        logger.error("RESEND_API_KEY is not configured.")
        return False

    # Use a verified sender address configured in Render.
    sender = os.getenv("EMAIL_FROM", "onboarding@resend.dev")

    resend.api_key = api_key

    message = {
        "from": sender,
        "to": [to_email],
        "subject": "Your Baller verification code",
        "text": (
            f"Hi {name},\n\n"
            f"Your Baller verification code is {code}.\n"
            "It expires in 15 minutes. "
            "If you didn't sign up, you can ignore this email.\n\n"
            "The Baller Team"
        ),
        "html": f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto;">
            <h2>Welcome to Baller!</h2>
            <p>Hi {name},</p>
            <p>Use this code to verify your email address:</p>
            <h1 style="letter-spacing: 8px;">{code}</h1>
            <p>This code expires in 15 minutes.</p>
            <p>If you didn't sign up, you can ignore this email.</p>
            <p>The Baller Team</p>
        </div>
        """,
    }

    try:
        result = resend.Emails.send(message)
        logger.info("Verification email accepted by Resend for %s", to_email)
        return bool(result)

    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
        return False
