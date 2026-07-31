"""Outbound email — currently a stub.

No SMTP credentials exist yet (waiting on Mark's mail server details). Until
SMTP_HOST is set, send_email() logs what it would have sent and returns without
attempting a connection. The call site (app/main.py's contact() endpoint) never
needs to change once real credentials land — just set the env vars below.
"""
import os
import smtplib
from email.message import EmailMessage

def contact_notify_email() -> str:
    """Staff inbox that gets notified of new contact-form submissions."""
    return os.environ.get("CONTACT_NOTIFY_EMAIL", "").strip()


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True if sent, False if skipped or failed —
    never raises, so a missing/unreachable mail server can't break the request that
    triggered it."""
    smtp_host = os.environ.get("SMTP_HOST", "").strip()
    if not smtp_host or not to:
        print(f"[email] SMTP not configured — would send to {to!r}: {subject!r}")
        return False
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_password = os.environ.get("SMTP_PASSWORD", "").strip()
    smtp_from = os.environ.get("SMTP_FROM", "").strip() or smtp_user
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_from
    msg["To"] = to
    msg.set_content(body)
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"[email] send to {to!r} failed: {exc}")
        return False
