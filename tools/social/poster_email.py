"""
poster_email.py — Send newsletter emails via Gmail SMTP (Phase 1).

Backend: Gmail SMTP with App Password (most reliable, no additional dependencies).
Future: Set EMAIL_BACKEND=sendgrid to use SendGrid free tier (100/day).

Gmail App Password setup:
  1. Enable 2-factor auth on your Google account
  2. Go to: myaccount.google.com → Security → App passwords
  3. Create app password for "Mail" on "Windows Computer"
  4. Copy the 16-char password → paste as SMTP_PASSWORD in .env
  (Do NOT use your regular Gmail password)

Email structure:
  - Sends individually to each subscriber (not BCC) for personalization
  - Includes first_name if available
  - Footer includes unsubscribe mailto link
  - Batches sends (50 per batch, 2s delay) to avoid provider rate limits
  - HTML + plain text fallback in multipart email
"""

import os
import time
import smtplib
import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "smtp")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FROM_NAME = os.getenv("EMAIL_FROM_NAME", os.getenv("SOCIAL_BRAND_NAME",
                       os.getenv("BROKER_COMPANY", "Valar Brokers")))
FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", SMTP_USER)
BRAND_NAME = os.getenv("SOCIAL_BRAND_NAME", os.getenv("BROKER_COMPANY", "Valar Brokers"))
WEBSITE_URL = os.getenv("SOCIAL_WEBSITE_URL", "")

BATCH_SIZE = 50
BATCH_DELAY = 2.0  # seconds between batches


# ── EMAIL BUILDER ─────────────────────────────────────────────────────────────

def _html_to_plain(html: str) -> str:
    """Convert simple HTML to plain text fallback."""
    import re
    # Remove tags
    plain = re.sub(r"<[^>]+>", " ", html)
    # Clean up whitespace
    plain = re.sub(r"\s+", " ", plain).strip()
    return plain


def build_html_email(subject: str, body_html: str,
                     subscriber: dict,
                     unsubscribe_email: str = None) -> tuple:
    """
    Build a complete HTML email with inline styles, header, and footer.

    Args:
        subject: Email subject line
        body_html: Article HTML (e.g. <h2>...</h2><p>...</p>)
        subscriber: dict with email, first_name (optional)
        unsubscribe_email: email address for mailto unsubscribe link

    Returns:
        Tuple of (html_string, plain_text_string)
    """
    first_name = subscriber.get("first_name", "")
    greeting = f"Hi {first_name}," if first_name else "Hi there,"
    unsubscribe_mailto = f"mailto:{unsubscribe_email or FROM_ADDRESS}?subject=Unsubscribe"
    website_link = f'<a href="{WEBSITE_URL}">{WEBSITE_URL}</a>' if WEBSITE_URL else BRAND_NAME

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{subject}</title>
</head>
<body style="margin:0;padding:0;background-color:#f5f5f5;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5;">
<tr><td align="center" style="padding:20px 10px;">
<table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <!-- Header -->
  <tr><td style="background-color:#1a1a2e;padding:24px 32px;text-align:center;">
    <span style="color:#ffffff;font-size:22px;font-weight:bold;letter-spacing:0.5px;">{BRAND_NAME}</span>
  </td></tr>

  <!-- Greeting -->
  <tr><td style="padding:28px 32px 8px;">
    <p style="margin:0;color:#333333;font-size:16px;">{greeting}</p>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:8px 32px 24px;color:#444444;font-size:15px;line-height:1.7;">
    {body_html}
  </td></tr>

  <!-- Divider -->
  <tr><td style="padding:0 32px;"><hr style="border:none;border-top:1px solid #eeeeee;"></td></tr>

  <!-- Footer -->
  <tr><td style="padding:20px 32px;text-align:center;color:#999999;font-size:12px;">
    <p style="margin:0 0 6px;">{website_link}</p>
    <p style="margin:0;">You received this because you subscribed to {BRAND_NAME} updates.
      <a href="{unsubscribe_mailto}" style="color:#999999;">Unsubscribe</a>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""

    plain = f"{greeting}\n\n{_html_to_plain(body_html)}\n\n---\n{BRAND_NAME}\n{WEBSITE_URL}\n\nTo unsubscribe, reply with 'Unsubscribe'."
    return html, plain


# ── SMTP SENDER ───────────────────────────────────────────────────────────────

def _send_via_smtp(subscribers: list, subject: str, body_html: str) -> dict:
    """
    Send newsletter to all subscribers via SMTP in batches.

    Returns:
        dict with 'sent', 'failed', 'skipped', 'errors' keys.
    """
    if not SMTP_USER:
        raise RuntimeError(
            "SMTP_USER not set in .env. Add your Gmail address as SMTP_USER."
        )
    if not SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_PASSWORD not set in .env.\n"
            "Use a Gmail App Password (not your regular password).\n"
            "Setup: myaccount.google.com → Security → App passwords"
        )

    sent = 0
    failed = 0
    errors = []

    print(f"  [EMAIL] Connecting to {SMTP_HOST}:{SMTP_PORT}...")
    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.ehlo()
            server.starttls()

        server.login(SMTP_USER, SMTP_PASSWORD)
        print(f"  [EMAIL] Authenticated. Sending to {len(subscribers)} subscribers...")

        for i, subscriber in enumerate(subscribers):
            try:
                email_addr = subscriber.get("email", "")
                if not email_addr:
                    failed += 1
                    continue

                html_body, plain_body = build_html_email(
                    subject, body_html, subscriber,
                    unsubscribe_email=FROM_ADDRESS
                )

                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = formataddr((FROM_NAME, FROM_ADDRESS))
                msg["To"] = email_addr

                msg.attach(MIMEText(plain_body, "plain", "utf-8"))
                msg.attach(MIMEText(html_body, "html", "utf-8"))

                server.sendmail(FROM_ADDRESS, email_addr, msg.as_string())
                sent += 1

                # Batch delay
                if (i + 1) % BATCH_SIZE == 0:
                    print(f"  [EMAIL] Sent {i+1}/{len(subscribers)}, pausing {BATCH_DELAY}s...")
                    time.sleep(BATCH_DELAY)

            except smtplib.SMTPRecipientsRefused as e:
                failed += 1
                errors.append(f"{subscriber.get('email')}: recipient refused")
            except Exception as e:
                failed += 1
                errors.append(f"{subscriber.get('email')}: {e}")

        server.quit()

    except smtplib.SMTPAuthenticationError:
        raise RuntimeError(
            "Gmail authentication failed.\n"
            "Make sure you're using an App Password (not your regular password).\n"
            "Setup: myaccount.google.com → Security → App passwords\n"
            "Also check that SMTP_USER matches the Gmail account."
        )
    except Exception as e:
        raise RuntimeError(f"SMTP error: {e}")

    print(f"  [EMAIL] Done: {sent} sent, {failed} failed")
    return {"sent": sent, "failed": failed, "errors": errors[:10]}


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def post_to_email(subscribers: list, subject: str, html_body: str) -> dict:
    """
    Send newsletter to all active subscribers.

    Args:
        subscribers: list of dicts with 'email', 'first_name' (optional)
        subject: email subject line
        html_body: HTML article content

    Returns:
        dict with 'platform', 'status', 'sent', 'failed', 'errors'
    """
    if not subscribers:
        print("  [EMAIL] No active subscribers. Add some with --add-subscriber")
        return {
            "platform": "email",
            "status": "skipped",
            "sent": 0,
            "failed": 0,
            "errors": ["No active subscribers"],
        }

    print(f"  [EMAIL] Preparing newsletter: '{subject}' → {len(subscribers)} subscribers")

    try:
        if EMAIL_BACKEND == "smtp":
            result = _send_via_smtp(subscribers, subject, html_body)
        else:
            raise RuntimeError(
                f"Unknown EMAIL_BACKEND='{EMAIL_BACKEND}'. "
                "Only 'smtp' is supported in Phase 1."
            )

        return {
            "platform": "email",
            "status": "posted" if result["sent"] > 0 else "failed",
            **result,
        }

    except Exception as e:
        print(f"  [EMAIL] Failed: {e}")
        return {
            "platform": "email",
            "status": "failed",
            "sent": 0,
            "failed": len(subscribers),
            "errors": [str(e)],
        }


def test_smtp_connection() -> bool:
    """
    Test SMTP connection and authentication without sending any emails.

    Returns True if successful, False if not.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        print("  SMTP_USER or SMTP_PASSWORD not set in .env")
        return False

    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            server.ehlo()
            server.starttls()

        server.login(SMTP_USER, SMTP_PASSWORD)
        server.quit()
        return True

    except smtplib.SMTPAuthenticationError:
        print("  Authentication failed. Check SMTP_USER/SMTP_PASSWORD in .env")
        print("  Gmail: use App Password at myaccount.google.com → Security → App passwords")
        return False
    except Exception as e:
        print(f"  SMTP connection failed: {e}")
        return False
