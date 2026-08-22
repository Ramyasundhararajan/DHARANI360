# -*- coding: utf-8 -*-
"""
DHARANI 360 - Sending mail
===========================
One place that knows how to send an email, so the compliance digest and the
password-reset link do not each carry their own copy of the SMTP dance.

Settings come from the environment first (a hosted deployment sets them in
.env), then from the Settings page in the portal (how a local install has
always configured it).

Nothing here decides *whether* to send - callers do that. This only sends,
and reports honestly when it could not.
"""
import config
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class MailNotConfigured(Exception):
    """No SMTP host or no from-address; there is nowhere to send from."""


class MailFailed(Exception):
    """The server was configured but refused or could not be reached."""


def settings():
    """SMTP settings, environment first, then the portal's Settings page."""
    import db
    stored = db.get_settings()
    return {
        "host": config.SMTP_HOST or stored.get("smtp_host"),
        "port": int(config.SMTP_PORT or stored.get("smtp_port") or 587),
        "username": config.SMTP_USER or stored.get("smtp_username"),
        "password": config.SMTP_PASSWORD or stored.get("smtp_password"),
        "from_addr": (config.DIGEST_FROM or stored.get("digest_from")
                      or config.SMTP_USER or stored.get("smtp_username")),
        "use_tls": str(stored.get("smtp_use_tls", "1")) not in ("0", "false", "False", ""),
    }


def is_configured():
    s = settings()
    return bool(s["host"] and s["from_addr"])


def send(to_addr, subject, html, text=None):
    """Send one message. Raises MailNotConfigured or MailFailed."""
    s = settings()
    if not s["host"] or not s["from_addr"]:
        raise MailNotConfigured(
            "No SMTP host or from-address is set. Fill them in on the "
            "Settings page, or set SMTP_HOST and DIGEST_FROM in .env.")

    recipients = [a.strip() for a in str(to_addr).split(",") if a.strip()]
    if not recipients:
        raise MailNotConfigured("No recipient address.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = s["from_addr"]
    msg["To"] = ", ".join(recipients)
    if text:
        msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        server = smtplib.SMTP(s["host"], s["port"], timeout=20)
        if s["use_tls"]:
            server.starttls(context=ssl.create_default_context())
        if s["username"]:
            server.login(s["username"], s["password"])
        server.sendmail(s["from_addr"], recipients, msg.as_string())
        server.quit()
        return True
    except Exception as exc:
        raise MailFailed(str(exc))


# ---------------------------------------------------------------------------
# The one message this module composes itself
# ---------------------------------------------------------------------------

RESET_SUBJECT = "DHARANI 360 - reset your password"

RESET_HTML = """\
<div style="font-family:Roboto,Arial,sans-serif;font-size:15px;color:#22303a;
            line-height:1.55;max-width:520px">
  <p style="font-size:18px;font-weight:600;margin:0 0 16px">Reset your DHARANI 360 password</p>
  <p style="margin:0 0 16px">Hello {name},</p>
  <p style="margin:0 0 16px">
    Someone asked to reset the password for this account. If that was you,
    use the link below. It works once, and stops working in {minutes} minutes.
  </p>
  <p style="margin:0 0 22px">
    <a href="{link}" style="display:inline-block;background:#0e7490;color:#ffffff;
       text-decoration:none;padding:11px 20px;border-radius:6px;font-weight:600">
      Set a new password</a>
  </p>
  <p style="margin:0 0 16px;color:#5c6b73;font-size:13px">
    If the button does not work, paste this into your browser:<br>
    <span style="word-break:break-all">{link}</span>
  </p>
  <p style="margin:0 0 16px;color:#5c6b73;font-size:13px">
    <strong>If you did not ask for this,</strong> you can ignore this email -
    your password has not changed. The request was recorded in the audit trail.
  </p>
  <p style="margin:24px 0 0;color:#8a979e;font-size:12px">
    DHARANI 360 &middot; Realty Operations &amp; Compliance Suite
  </p>
</div>
"""

RESET_TEXT = """\
Reset your DHARANI 360 password

Hello {name},

Someone asked to reset the password for this account. If that was you, open
the link below. It works once, and stops working in {minutes} minutes.

{link}

If you did not ask for this, you can ignore this email - your password has
not changed. The request was recorded in the audit trail.
"""


def send_password_reset(to_addr, name, link, minutes):
    return send(
        to_addr,
        RESET_SUBJECT,
        RESET_HTML.format(name=name or "there", link=link, minutes=minutes),
        RESET_TEXT.format(name=name or "there", link=link, minutes=minutes),
    )
