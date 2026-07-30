"""Outbound email — currently a stub.

No SMTP credentials exist yet (waiting on Mark's mail server details). Until
SMTP_HOST is set, send_email() logs what it would have sent and returns without
attempting a connection. The call site (app/main.py's contact() endpoint) never
needs to change once real credentials land — just set the env vars below.
"""
import os
import smtplib
from email.message import EmailMessage

SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("SMTP_FROM", "").strip() or SMTP_USER
# Staff inbox that gets notified of new contact-form submissions.
CONTACT_NOTIFY_EMAIL = os.environ.get("CONTACT_NOTIFY_EMAIL", "").strip()


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True if sent, False if skipped or failed —
    never raises, so a missing/unreachable mail server can't break the request that
    triggered it."""
    if not SMTP_HOST or not to:
        print(f"[email] SMTP not configured — would send to {to!r}: {subject!r}")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"[email] send to {to!r} failed: {exc}")
        return False
