"""DHARANI 360 -> n8n event hook.

The registers already know everything that happens. This is the one wire that
tells somebody else about it, the moment it happens, instead of waiting for a
scheduled scan to notice.

It is deliberately timid:

  * it never blocks a save - the POST happens on a background thread
  * it never raises - a broken or missing n8n cannot stop a form submitting
  * it sends nothing at all unless N8N_BASE_URL is set, so an installation
    that does not use n8n behaves exactly as it did before

Configure in .env:

    N8N_BASE_URL=https://your-n8n-host          # no trailing slash
    N8N_EVENT_TOKEN=a-long-random-string        # optional shared secret
    N8N_TIMEOUT=4                               # seconds

Generate a token with:

    python -c "import secrets; print(secrets.token_urlsafe(32))"

and set the same value in n8n on the webhook node's Header Auth credential
(header name: X-Dharani-Token).
"""

import json
import os
import threading
import urllib.error
import urllib.request

BASE = (os.environ.get("N8N_BASE_URL") or "").rstrip("/")
TOKEN = os.environ.get("N8N_EVENT_TOKEN", "")
TIMEOUT = float(os.environ.get("N8N_TIMEOUT", "4"))

# Which n8n webhook paths hear about which events. Add a path here and the
# flow listening on it starts receiving, with nothing else to change.
ROUTES = {
    "record.created": ["/webhook/dharani/record-created", "/webhook/dharani/event"],
    "record.changed": ["/webhook/dharani/event"],
    "record.deleted": ["/webhook/dharani/event"],
}

# Registers whose contents are too sensitive to leave the building in a
# webhook body. The event still fires - the field values do not travel.
REDACT_FORMS = {"HR-002", "PAY-001", "PAY-002", "PAY-003", "FIN-007",
                "IT-006", "CMP-003", "CMP-004"}
REDACT_FIELDS = {"passport_no", "emirates_id_no", "bank_account_iban",
                 "bank_name", "basic_salary", "old_bank_details",
                 "new_bank_details", "password", "salary"}


def enabled():
    return bool(BASE)


def _actor():
    """Whoever is signed in, if we happen to be inside a request."""
    try:
        from flask import session
        return session.get("full_name") or session.get("username") or "portal"
    except Exception:
        return "portal"


def _clean(form_code, data):
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if k in REDACT_FIELDS:
            out[k] = "[redacted]"
        elif form_code in REDACT_FORMS and k not in (
                "full_name", "employee_name", "position", "department",
                "start_date", "email", "visa_expiry", "vendor_name",
                "status", "leave_type", "from_date", "to_date", "days"):
            out[k] = "[redacted]"
        else:
            out[k] = "" if v is None else str(v)[:500]
    return out


def _post(url, payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("X-Dharani-Token", TOKEN)
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT).read()
    except Exception:
        # A webhook that cannot be reached is not an error the person filling
        # in a form should ever see. The scheduled flows still catch up.
        pass


def emit(event, form_code, record_id, doc_no, data=None,
         actor=None, changed_fields=None):
    """Fire and forget. Safe to call from anywhere, including inside a
    database transaction - it does no database work of its own."""
    if not enabled():
        return
    payload = {
        "event": event,
        "form_code": form_code,
        "record_id": record_id,
        "doc_no": doc_no,
        "actor": actor or _actor(),
        "data": _clean(form_code, data or {}),
    }
    if changed_fields:
        payload["changed_fields"] = {
            k: ("[redacted]" if k in REDACT_FIELDS else v)
            for k, v in changed_fields.items()}
    for path in ROUTES.get(event, []):
        # Not a daemon thread: a short-lived script (email_digest.py,
        # setup scripts) must not exit before the event has actually left.
        threading.Thread(target=_post, args=(BASE + path, payload),
                         daemon=False).start()


if __name__ == "__main__":
    # python n8n_hooks.py   - send one test event and say what happened.
    if not enabled():
        print("N8N_BASE_URL is not set. Nothing would be sent.")
    else:
        print("Sending a test event to:")
        for p in ROUTES["record.created"]:
            print("   ", BASE + p)
        emit("record.created", "COR-001", 0, "DR-COR-001-TEST",
             {"document_name": "Test from n8n_hooks.py"}, actor="setup test")
        import time
        time.sleep(TIMEOUT + 1)
        print("Sent. Check the executions list in n8n.")
