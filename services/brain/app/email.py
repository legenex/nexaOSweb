"""Outbound email via SMTP.

This is the Brain's only mail path. Credentials are read from the server side settings and never
leave the server. When no SMTP host is configured the mailer is disabled: send_email logs the
message (including any link in the body) at WARNING and returns False, so flows that depend on
email, such as password reset, still work end to end in local dev without a mail server. In that
mode an operator can read the reset link straight from the Brain log.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.settings import Settings, get_settings

logger = logging.getLogger("nexaos.email")


def email_enabled(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.nexa_smtp_host)


def _from_address(settings: Settings) -> str:
    # Prefer an explicit From, fall back to the SMTP user, then a sane default.
    return settings.nexa_smtp_from or settings.nexa_smtp_user or "no-reply@localhost"


def send_email(to: str, subject: str, body: str, settings: Settings | None = None) -> bool:
    """Send a plain text email. Returns True if handed to the SMTP server, False if disabled.

    Never raises on a delivery problem: a failure is logged and reported as False so callers (the
    password reset request in particular) can keep their no enumeration, always 204 contract.
    """
    settings = settings or get_settings()

    if not email_enabled(settings):
        logger.warning(
            "SMTP not configured, email to %s not sent. Subject: %s\n%s", to, subject, body
        )
        return False

    message = EmailMessage()
    message["From"] = _from_address(settings)
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(settings.nexa_smtp_host, settings.nexa_smtp_port, timeout=15) as client:
            if settings.nexa_smtp_starttls:
                client.starttls()
            if settings.nexa_smtp_user:
                client.login(settings.nexa_smtp_user, settings.nexa_smtp_password)
            client.send_message(message)
        logger.info("sent email to %s, subject: %s", to, subject)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("failed to send email to %s: %s", to, exc)
        return False
