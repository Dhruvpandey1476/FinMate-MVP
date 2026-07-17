"""
Email service — sends magic login links.

Uses Resend (free tier: 3,000 emails/mo) if RESEND_API_KEY is set; otherwise
runs in DEV mode: logs the link and returns it to the caller so you can test
without configuring any email provider.
"""
import os
import logging
import httpx

logger = logging.getLogger("finmate.email")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "FinMate <onboarding@resend.dev>")


def email_configured() -> bool:
    return bool(RESEND_API_KEY)


def send_magic_link(to_email: str, link: str) -> bool:
    """Returns True if an email was actually sent. In DEV mode returns False."""
    if not RESEND_API_KEY:
        logger.warning("DEV MODE — magic link for %s: %s", to_email, link)
        return False
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": FROM_EMAIL,
                "to": [to_email],
                "subject": "Your FinMate login link",
                "html": (
                    f"<p>Tap to log in to FinMate:</p>"
                    f'<p><a href="{link}">Log in to FinMate</a></p>'
                    f"<p>This link expires in 20 minutes. If you didn't request it, ignore this email.</p>"
                ),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("Failed to send magic link to %s: %s", to_email, e)
        return False
