# -*- coding: utf-8 -*-
"""
DHARANI 360 - smoke test
=========================
Signs in, walks every GET route the signed-in Director can reach, and runs a
create / edit / delete cycle through the real HTTP routes. Then checks that
the audit trail recorded what happened.

Run it against SQLite (the default):

    python smoketest.py

Or against Postgres, which is what a deployed install uses:

    DATABASE_URL=postgresql://user:pw@host:5432/dharani360 python smoketest.py

Exits non-zero if anything failed, so it can gate a deploy.
"""
import os
import re
import sys
import shutil
import tempfile

# A test run must never touch a real instance/ directory.
if not os.environ.get("D360_SMOKE_KEEP"):
    _tmp = tempfile.mkdtemp(prefix="d360-smoke-")
    os.environ.setdefault("D360_SMOKE_TMP", _tmp)

import dbcompat  # noqa: E402
import db  # noqa: E402
import app as app_module  # noqa: E402
from forms_data import FORMS, DEPARTMENTS  # noqa: E402
import supabase_auth  # noqa: E402

FAILURES = []
CHECKS = [0]

TEST_EMAIL = (supabase_auth.ALLOWED_EMAILS[0]
              if getattr(supabase_auth, "ALLOWED_EMAILS", None) else "admin@example.com")
START_PASSWORD = "dharani360"
NEW_PASSWORD = "SmokeTest!2468"


def check(label, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print("  ok    {}".format(label))
    else:
        print("  FAIL  {} {}".format(label, detail))
        FAILURES.append(label)
    return bool(condition)


def token(client, path):
    resp = client.get(path)
    m = re.search(rb'name="_csrf" value="([^"]+)"', resp.data)
    return m.group(1).decode() if m else None


def main():
    print("DHARANI 360 smoke test")
    print("engine:", dbcompat.describe())
    print()

    client = app_module.app.test_client()

    # ---- sign in --------------------------------------------------------
    print("Sign-in and CSRF")
    admin = db.get_user_by_username("admin")
    if admin is None:
        print("  FAIL  no admin account was seeded")
        return 1
    db.set_user_email(admin["id"], TEST_EMAIL)

    r = client.post("/login", data={"email": TEST_EMAIL, "password": START_PASSWORD})
    check("POST without a CSRF token is refused", r.status_code == 400,
          "(got {})".format(r.status_code))

    r = client.post("/login", data={"email": TEST_EMAIL, "password": START_PASSWORD,
                                    "_csrf": token(client, "/login")})
    if not check("sign in", r.status_code == 302, "(got {})".format(r.status_code)):
        return 1

    r = client.post("/account/change-password",
                    data={"current_password": START_PASSWORD,
                          "new_password": NEW_PASSWORD,
                          "confirm_password": NEW_PASSWORD,
                          "_csrf": token(client, "/account/change-password")})
    check("set own password", r.status_code == 302, "(got {})".format(r.status_code))

    r = client.get("/")
    check("security headers present",
          r.headers.get("X-Frame-Options") and r.headers.get("X-Content-Type-Options"))

    # ---- health check ---------------------------------------------------
    print("\nHealth check")
    r = client.get("/healthz")
    body = r.get_json() or {}
    check("GET /healthz answers without a sign-in", r.status_code == 200,
          "(got {})".format(r.status_code))
    check("it reports the database as reachable", body.get("checks", {}).get("database") == "ok")
    check("it says nothing it should not",
          not any(k in str(body).lower() for k in ("postgres://", "password", "secret")))

    # ---- sign-in throttling ---------------------------------------------
    print("\nSign-in throttling")
    throttle_email = "attacker@example.com"
    db.clear_login_failures(throttle_email)
    for _ in range(db.LOGIN_MAX_ATTEMPTS + 1):
        client.post("/login", data={"email": throttle_email, "password": "guess",
                                    "_csrf": token(client, "/login")})
    check("repeated failures lock the address out", db.login_locked_for(throttle_email) > 0)
    check("the lockout is recorded in the audit trail",
          any(a["action"] == "login.blocked" for a in db.list_audit(action="login.blocked")))
    db.clear_login_failures(throttle_email)
    check("a successful sign-in clears the count",
          db.recent_login_failures(throttle_email) == 0)

    # ---- every page a Director can open ---------------------------------
    print("\nPages")
    pages = ["/", "/me", "/calendar", "/search?q=a", "/calls", "/chat", "/files",
             "/todos", "/notes", "/profile", "/users", "/settings", "/login-activity",
             "/regulations", "/documentation", "/insights-center", "/dashboards",
             "/projects/kanban", "/audit"]
    for path in pages:
        r = client.get(path)
        check("GET {}".format(path), r.status_code == 200, "(got {})".format(r.status_code))

    for dept in DEPARTMENTS:
        r = client.get("/department/{}".format(dept["code"]))
        if r.status_code != 200:
            check("GET /department/{}".format(dept["code"]), False,
                  "(got {})".format(r.status_code))
    check("every department page opens",
          not [f for f in FAILURES if f.startswith("GET /department/")])

    # ---- every register and blank form ----------------------------------
    print("\nRegisters and forms ({} of them)".format(len(FORMS)))
    bad_registers, bad_forms = [], []
    for form in FORMS:
        if client.get("/register/{}".format(form["code"])).status_code != 200:
            bad_registers.append(form["code"])
        if client.get("/form/{}".format(form["code"])).status_code != 200:
            bad_forms.append(form["code"])
    check("every register opens", not bad_registers, "broken: {}".format(bad_registers[:6]))
    check("every blank form opens", not bad_forms, "broken: {}".format(bad_forms[:6]))

    # ---- create / edit / delete through the real routes -----------------
    print("\nRecord lifecycle")
    code = "COR-002"
    payload = {"licence_permit": "Trade Licence", "authority": "DET",
               "reference_no": "SMOKE-0001", "issue_date": "2025-09-16",
               "expiry_date": "2026-09-15", "renewal_lead_time_days": "90",
               "responsible_person": "Smoke Test", "status": "Valid",
               "notes": "created by smoketest"}
    before_count = db.count_records(code)
    payload["_csrf"] = token(client, "/form/{}".format(code))
    r = client.post("/form/{}".format(code), data=payload)
    check("create a record", r.status_code == 302 and db.count_records(code) == before_count + 1)

    rows, _ = db.get_records(code)
    row = next((x for x in rows if x["reference_no"] == "SMOKE-0001"), None)
    if not check("the new record is in the register", row is not None):
        return 1
    rid = row["id"]

    check("record page opens", client.get("/record/{}/{}".format(code, rid)).status_code == 200)
    check("record PDF renders",
          client.get("/record/{}/{}/sheet.pdf".format(code, rid)).status_code == 200)
    check("register CSV exports",
          client.get("/register/{}/export.csv".format(code)).status_code == 200)
    check("register PDF exports",
          client.get("/register/{}/export.pdf".format(code)).status_code == 200)
    check("global search finds it", len(db.global_search("SMOKE-0001")) >= 1)

    payload.update({"_csrf": token(client, "/record/{}/{}/edit".format(code, rid)),
                    "reference_no": "SMOKE-0002",
                    "status": "Renewal In Progress"})
    r = client.post("/record/{}/{}/edit".format(code, rid), data=payload)
    check("edit the record", r.status_code == 302)

    # ---- the audit trail ------------------------------------------------
    print("\nAudit trail")
    trail = db.list_audit(form_code=code, record_id=rid)
    actions = [a["action"] for a in trail]
    fields = {a["field_name"] for a in trail if a["field_name"]}
    check("the creation was recorded", "create" in actions)
    check("the edit was recorded", "update" in actions)
    check("the changed field is named", "reference_no" in fields,
          "(recorded: {})".format(sorted(fields)))
    changed = next((a for a in trail if a["field_name"] == "reference_no"), None)
    check("before and after values are kept",
          changed is not None and changed["old_value"] == "SMOKE-0001"
          and changed["new_value"] == "SMOKE-0002")
    check("the change is attributed", changed is not None and changed["actor"] == "admin")
    check("unchanged fields are not logged as edits",
          "renewal_lead_time_days" not in fields,
          "(a REAL column read back as 90.0 must not look like an edit)")

    r = client.post("/record/{}/{}/delete".format(code, rid),
                    data={"_csrf": token(client, "/record/{}/{}".format(code, rid))})
    check("delete the record", r.status_code == 302)
    check("the deletion was recorded",
          "delete" in [a["action"] for a in db.list_audit(form_code=code, record_id=rid)])
    check("sign-in was recorded", db.audit_count() > 0
          and any(a["action"] == "login" for a in db.list_audit(action="login")))
    check("the audit page opens", client.get("/audit").status_code == 200)

    # ---- summary --------------------------------------------------------
    print()
    if FAILURES:
        print("{} of {} checks FAILED:".format(len(FAILURES), CHECKS[0]))
        for f in FAILURES:
            print("   - {}".format(f))
        return 1
    print("all {} checks passed on {}".format(CHECKS[0], dbcompat.engine_name()))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        tmp = os.environ.get("D360_SMOKE_TMP")
        if tmp and os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
