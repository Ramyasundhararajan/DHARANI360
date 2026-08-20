# -*- coding: utf-8 -*-
"""
DHARANI 360 - Compliance digest emailer
==========================================
Sends a RED/AMBER digest of everything expiring soon, using the SMTP
settings configured in the portal's Settings page (Director login only).

This script does NOT need the web app to be running - it reads the same
database file directly. Run it manually to test:

    python email_digest.py

Or schedule it to run automatically every morning with Windows Task
Scheduler (see README.md, section "Automated compliance email reminders").
Exit code 0 = sent (or nothing to report and that's fine); non-zero = a
real error worth looking at.
"""
import smtplib
import ssl
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import db


def build_digest_html(horizon_days):
    items = db.expiring_items(horizon_days=horizon_days)
    red = [i for i in items if i["rag"] == "RED"]
    amber = [i for i in items if i["rag"] == "AMBER"]

    def rows_html(items_list):
        if not items_list:
            return "<p style='color:#888;'>None.</p>"
        out = "<table cellspacing='0' cellpadding='6' style='border-collapse:collapse;width:100%;'>"
        out += "<tr style='background:#f1f1f1;text-align:left;'><th>Days</th><th>Doc No.</th><th>Register</th><th>Department</th><th>Expiry</th></tr>"
        for i in items_list:
            days = "{}d overdue".format(-i["days_left"]) if i["days_left"] < 0 else "{}d".format(i["days_left"])
            out += ("<tr style='border-bottom:1px solid #eee;'><td>{}</td><td>{}</td><td>{}</td>"
                    "<td>{}</td><td>{}</td></tr>").format(days, i["doc_no"], i["form_title"], i["dept"], i["expiry_date"])
        out += "</table>"
        return out

    html = """
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:700px;">
      <h2 style="margin-bottom:0;">DHARANI 360 &mdash; Daily Compliance Digest</h2>
      <p style="color:#666;margin-top:4px;">Everything due or overdue within {horizon} days.</p>
      <h3 style="color:#c0392b;">&#128308; Urgent (&le;30 days / overdue) &mdash; {red_n}</h3>
      {red_html}
      <h3 style="color:#e67e22;">&#128992; Upcoming (31&ndash;90 days) &mdash; {amber_n}</h3>
      {amber_html}
      <p style="color:#999;font-size:12px;margin-top:24px;">Sent automatically by DHARANI 360, running on this computer. Open the Admin Control Tower for full detail.</p>
    </div>
    """.format(horizon=horizon_days, red_n=len(red), amber_n=len(amber),
               red_html=rows_html(red), amber_html=rows_html(amber))
    return html, len(red), len(amber)


def send_digest(force=False):
    settings = db.get_settings()
    host = settings.get("smtp_host")
    to_addr = settings.get("digest_to")
    from_addr = settings.get("digest_from") or settings.get("smtp_username")
    horizon = int(settings.get("digest_horizon_days") or 90)

    if not host or not to_addr:
        print("Email digest is not configured yet. Open the portal's Settings page "
              "(Director login) and fill in SMTP host and recipient address.")
        return False

    html, red_n, amber_n = build_digest_html(horizon)
    if red_n == 0 and amber_n == 0 and not force:
        print("Nothing red or amber right now - no email sent. (Run with --force to send anyway.)")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "DHARANI 360 - Compliance Digest ({} urgent, {} upcoming)".format(red_n, amber_n)
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html, "html"))

    port = int(settings.get("smtp_port") or 587)
    use_tls = str(settings.get("smtp_use_tls", "1")) not in ("0", "false", "False", "")

    try:
        server = smtplib.SMTP(host, port, timeout=20)
        if use_tls:
            server.starttls(context=ssl.create_default_context())
        username = settings.get("smtp_username")
        password = settings.get("smtp_password")
        if username:
            server.login(username, password)
        server.sendmail(from_addr, [a.strip() for a in to_addr.split(",") if a.strip()], msg.as_string())
        server.quit()
        print("Digest sent to {}: {} urgent, {} upcoming.".format(to_addr, red_n, amber_n))
        return True
    except Exception as exc:  # noqa
        print("Failed to send digest: {}".format(exc))
        return False


if __name__ == "__main__":
    ok = send_digest(force="--force" in sys.argv)
    sys.exit(0 if ok else 1)
