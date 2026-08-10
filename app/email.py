"""Outbound email.

Until SMTP_HOST is set, send_email() logs what it would have sent and returns
without attempting a connection. The call site (app/main.py's contact() endpoint)
never needs to change — just set the env vars below.

print(..., flush=True): this runs inside a FastAPI BackgroundTasks call, so its
output is often the only thing printed for a long stretch — under Docker, stdout
is block- not line-buffered when not a TTY, so a low-volume message like this can
sit unflushed in Coolify's logs indefinitely without an explicit flush.
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
        print(f"[email] SMTP not configured — would send to {to!r}: {subject!r}", flush=True)
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
            # SMTP_DEBUG=1 traces the full wire protocol (EHLO/STARTTLS/AUTH/MAIL FROM/
            # RCPT TO/DATA and every server response) to stdout — noisy, so it's opt-in.
            # Useful for a relay that accepts the message (no exception, no refused
            # recipients) but never actually delivers it: that failure happens on a hop
            # this process can't see, so the wire trace is the most this code can ever
            # tell you short of checking the relay's own mail log.
            if os.environ.get("SMTP_DEBUG", "").strip():
                server.set_debuglevel(2)
            tls_code, tls_resp = server.starttls()
            print(f"[email] connected to {smtp_host}:{smtp_port} — STARTTLS {tls_code} {tls_resp!r}", flush=True)
            if smtp_user:
                login_code, login_resp = server.login(smtp_user, smtp_password)
                print(f"[email] AUTH as {smtp_user!r} — {login_code} {login_resp!r}", flush=True)
            # send_message() only raises for a fully-rejected send (e.g. every recipient
            # refused, or the server drops the connection). A PARTIAL refusal — some
            # recipients accepted, others not — returns normally with those recipients in
            # the result dict instead, so an unqualified "sent" can still mean only one of
            # two recipients actually got it. Surface that explicitly.
            refused = server.send_message(msg)
        if refused:
            print(f"[email] sent to {to!r} but SERVER REFUSED: {refused!r}", flush=True)
        else:
            print(f"[email] sent to {to!r}: {subject!r} — accepted by {smtp_host} for ALL recipients", flush=True)
        return True
    except smtplib.SMTPResponseException as exc:
        print(f"[email] send to {to!r} failed — SMTP {exc.smtp_code}: {exc.smtp_error!r}", flush=True)
        return False
    except Exception as exc:
        print(f"[email] send to {to!r} failed: {type(exc).__name__}: {exc}", flush=True)
        return False
