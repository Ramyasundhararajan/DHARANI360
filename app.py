# -*- coding: utf-8 -*-
"""
DHARANI 360 - Real Estate Operations, Compliance & Growth System
====================================================================
Run with:  python app.py
Then open: http://127.0.0.1:5000

Single-computer local system by design (see README.md). Every submitted
form becomes a permanent row in that form's register (SQLite table) -
"the form is merely the input, the register is the memory of the
company." Login required; each role sees only its departments (see
access.py). Records link to each other automatically wherever they share
a real-world key (lead, client, agent, property, transaction...).
"""
import os
import secrets
import io
import csv
import json
import calendar as cal_mod
from urllib.parse import urljoin, urlparse
from datetime import date, datetime
from flask import (Flask, render_template, request, redirect, url_for, flash,
                    Response, send_file, abort, g, make_response)

import db
import pdfout
import qrgen
import auth
import icons
import insights
import regulations_data
import supabase_auth
from access import ROLES, ROLE_NAMES, depts_for_role, is_admin_role, can_access_dept
from forms_data import (FORMS, FORMS_BY_CODE, DEPARTMENTS, DEPARTMENTS_BY_CODE,
                         forms_for_dept, group_fields)


def _load_secret_key():
    """The key that signs session cookies.

    Order: the SECRET_KEY environment variable (used when hosted), then a
    random key generated once and kept in instance/secret_key (used on a
    normal office PC). It is never written into the source, because the
    source goes to GitHub and anyone holding this key can forge a login.
    Deleting the file simply signs everyone out.
    """
    from_env = os.environ.get("SECRET_KEY")
    if from_env:
        return from_env
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance", "secret_key")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(48)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(key)
    except OSError:
        pass
    return key


app = Flask(__name__)
app.secret_key = _load_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20MB per request
app.config["TEMPLATES_AUTO_RELOAD"] = True

db.init_db()


@app.after_request
def _no_stale_pages(response):
    """Pages are built from live records, so a cached copy is always wrong.

    Static files are excluded - those are versioned by _stamp_static above
    and should stay cached.
    """
    if request.endpoint != "static":
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.url_defaults
def _stamp_static(endpoint, values):
    """Append the file's modification time to every /static/ URL.

    Without this the browser keeps serving the stylesheet it cached days
    ago, so a change is made, saved, and the page still looks identical
    after a refresh. With the timestamp in the URL the browser treats an
    edited file as a new file and fetches it, while an unchanged file is
    still served straight from the cache.
    """
    if endpoint != "static" or "filename" not in values:
        return
    path = os.path.join(app.static_folder, values["filename"])
    try:
        values["v"] = int(os.stat(path).st_mtime)
    except OSError:
        pass


@app.context_processor
def inject_globals():
    user = auth.current_user()
    allowed = auth.allowed_depts_for_current_user()
    visible_depts = [d for d in DEPARTMENTS if d["code"] in allowed]
    visible_dashboards = [d for d in insights.DASHBOARDS if d["dept"] is None or d["dept"] in allowed]
    counts = db.all_counts() if user else {}
    return {
        "DEPARTMENTS": visible_depts,
        "ALL_DEPARTMENTS": DEPARTMENTS,
        "DASHBOARDS_VISIBLE": visible_dashboards,
        "status_color": db.status_color,
        "current_user": user,
        "is_admin": is_admin_role(user["role"]) if user else False,
        "can_see_insights": bool(user and (is_admin_role(user["role"]) or user["role"] == "Manager")),
        "ROLES": ROLES,
        "icon": icons.svg,
        "dept_icon": icons.dept_icon,
        "form_icon": icons.form_icon,
        "dashboard_icon": icons.dashboard_icon,
        "forms_for_dept": forms_for_dept,
        "nav_counts": counts,
        "chat_unread": db.chat_unread_total(user["username"]) if user else 0,
        # Everyone you could share something with. Available everywhere so the
        # Share dialog can be dropped into any page without its route having to
        # know about sharing at all.
        "share_colleagues": ([u for u in db.list_users()
                              if u["username"] != user["username"] and u.get("active", 1)]
                             if user else []),
        "notifications": _notifications(user) if user else [],
        "today_label": date.today().strftime("%d %b %Y"),
        # _rules_strip.html is included from register, form and department
        # pages, so the obligation lookup has to be available everywhere
        # rather than passed by each individual route.
        "dept_obligations": regulations_data.for_dept,
        "dept_oblig_counts": regulations_data.counts_for_dept,
        "authority_marks": regulations_data.authority_marks,
        "authority_label": regulations_data.authority_label,
        "authority_logo": _authority_logo,
        "SEVERITY_TONE": regulations_data.SEVERITY_TONE,
        "SEVERITY_LABEL": regulations_data.SEVERITY_LABEL,
    }


@app.template_filter("tidy")
def _tidy_value(value):
    """Numeric columns are stored as REAL, so a plain "12" comes back as 12.0.
    Show whole numbers without the pointless decimal, and leave everything
    else exactly as it is."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.endswith(".0") and stripped[:-2].lstrip("-").isdigit():
            return stripped[:-2]
    return value


_AUTHORITY_LOGO_DIR = os.path.join(app.static_folder, "images", "authorities")


def _authority_logo(key):
    """Filename of an official logo for this authority, or None.

    The library ships monograms rather than government emblems, which are
    protected marks. If the company drops a licensed <key>.png / .svg into
    static/images/authorities/ it is picked up here with no code change - see
    the README in that folder. The directory listing is cached per process
    because this runs once per authority per card.
    """
    cache = getattr(_authority_logo, "_cache", None)
    if cache is None:
        cache = {}
        try:
            for name in os.listdir(_AUTHORITY_LOGO_DIR):
                stem, dot, ext = name.rpartition(".")
                if dot and ext.lower() in ("png", "svg", "jpg", "jpeg", "webp"):
                    cache.setdefault(stem.lower(), name)
        except OSError:
            pass
        _authority_logo._cache = cache
    return cache.get(key)


def _require_dept(dept_code):
    if not can_access_dept(auth.current_user()["role"], dept_code):
        abort(403)


# Chart series alternate between the logo's two halves — teal, copper, teal,
# copper — rather than running a single hue or a rainbow, so any multi-series
# chart carries the brand on its own. All eight clear 3:1 against white.
_PALETTE = ["#0e7490", "#6b4226", "#3f9aa2", "#a3703f",
            "#0b5c73", "#8a5a34", "#2c7f8c", "#7d4f2e"]
_STATUS_COLOR_VAR = {"GREEN": "var(--green)", "AMBER": "var(--amber)", "RED": "var(--red)",
                      "BLUE": "var(--blue)", "GREY": "var(--grey)"}


def _bars(counts, palette=None):
    """db.field_counts() output -> [{label,count,pct,color}] for the
    breakdown/donut/segbar chart macros, colored from a fixed palette."""
    total = sum(c["count"] for c in counts) or 1
    pal = palette or _PALETTE
    return [{"label": c["value"], "count": c["count"], "pct": round(100 * c["count"] / total),
              "color": pal[i % len(pal)]} for i, c in enumerate(counts)]


def _status_bars(counts):
    """Same as _bars() but colored by the record's status (RED/AMBER/GREEN/...)."""
    total = sum(c["count"] for c in counts) or 1
    return [{"label": c["value"], "count": c["count"], "pct": round(100 * c["count"] / total),
              "color": _STATUS_COLOR_VAR.get(db.status_color(c["value"]), "var(--accent)")} for c in counts]


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------


def _notifications(user):
    """Everything this person should look at, newest concern first.

    Deliberately assembled from what the registers already know rather than
    from a separate notifications table - nothing has to be written twice,
    and nothing can drift out of step with the records themselves.
    Each entry is {tone, icon, title, detail, url}. Tone drives the colour:
    red = act today, amber = act this week, blue = for information.
    """
    items = []
    today = date.today()

    # 1. Expiries and renewals, from every register that carries a date.
    try:
        allowed = set(auth.allowed_depts_for_current_user() or [])
        for it in db.expiring_items(horizon_days=60):
            if allowed and it["dept"] not in allowed:
                continue
            days = it["days_left"]
            if days < 0:
                tone, when = "red", "overdue by {} day{}".format(abs(days), "" if abs(days) == 1 else "s")
            elif days <= 30:
                tone, when = "red", "due in {} day{}".format(days, "" if days == 1 else "s")
            else:
                tone, when = "amber", "due in {} days".format(days)
            items.append({
                "tone": tone, "icon": "alert-triangle", "sort": days,
                "title": "{} {}".format(it["form_title"], it["doc_no"] or ""),
                "detail": "{} - {}".format(when, it["expiry_date"] or ""),
                "url": url_for("record_view", form_code=it["form_code"], record_id=it["record_id"]),
            })
    except Exception:
        pass

    # 2. Unread messages.
    try:
        unread = db.chat_unread_total(user["username"])
        if unread:
            items.append({
                "tone": "blue", "icon": "mail", "sort": -1000,
                "title": "{} unread message{}".format(unread, "" if unread == 1 else "s"),
                "detail": "in Chat", "url": url_for("chat"),
            })
    except Exception:
        pass

    # 3. Your own to-dos that are still open.
    try:
        open_todos = [t for t in db.list_todos(user["id"]) if t.get("status") != "Done"]
        if open_todos:
            items.append({
                "tone": "amber" if len(open_todos) > 4 else "blue",
                "icon": "clipboard-list", "sort": -500,
                "title": "{} task{} still open".format(len(open_todos), "" if len(open_todos) == 1 else "s"),
                "detail": open_todos[0]["text"][:70], "url": url_for("todos_page"),
            })
    except Exception:
        pass

    # 4. Meetings coming up.
    try:
        for m in db.list_meetings_upcoming(limit=5, since_iso=today.isoformat()):
            when = m["meeting_date"] or ""
            items.append({
                "tone": "blue", "icon": "calendar-check",
                "sort": -100 if when == today.isoformat() else -50,
                "title": m["title"],
                "detail": ("Today" if when == today.isoformat() else when) +
                          ((" at " + m["start_time"]) if m.get("start_time") else ""),
                "url": url_for("calendar"),
            })
    except Exception:
        pass

    items.sort(key=lambda x: x["sort"])
    return items[:25]



@app.route("/login", methods=["GET", "POST"])
def login():
    """Email sign-in, verified by Supabase, restricted to the allowlist.

    Three things must all hold: the address is on supabase_auth.ALLOWED_EMAILS,
    Supabase accepts the password, and a matching active local account exists.
    The local account is what carries the role and department access - Supabase
    only answers "is this really them".
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not supabase_auth.is_allowed(email):
            # Deliberately the same wording as a wrong password, so this is not
            # a way to discover which addresses exist.
            flash("Incorrect email or password.", "error")
            return render_template("login.html", supabase=supabase_auth.health())

        user = db.get_user_by_email(email)
        if not user or not user["active"]:
            flash("Incorrect email or password.", "error")
            return render_template("login.html", supabase=supabase_auth.health())

        signed_in = False
        try:
            supabase_auth.sign_in(email, password)
            signed_in = True
            # Cache the verified password so the office can still get in if the
            # connection drops later. See supabase_auth.offline_fallback_enabled.
            db.set_password(user["id"], auth.hash_password(password),
                            must_change_password=bool(user.get("must_change_password")))
        except ValueError:
            flash("Incorrect email or password.", "error")
        except supabase_auth.SupabaseNotConfigured:
            # A fresh install has no supabase_config.json yet. Refusing everyone
            # until it is filled in would mean the system cannot be opened at
            # all after an update, so the locally stored password is accepted
            # here too - with the state said plainly on screen.
            if auth.verify_password(password, user["password_hash"]):
                signed_in = True
                flash("Signed in with the local password - Supabase is not configured yet. "
                      "See SUPABASE_SETUP.md to switch sign-in over to Supabase.", "warning")
            else:
                flash("Incorrect email or password.", "error")
        except supabase_auth.SupabaseUnreachable:
            if supabase_auth.offline_fallback_enabled() and \
                    auth.verify_password(password, user["password_hash"]):
                signed_in = True
                flash("Signed in offline - Supabase could not be reached, so the "
                      "locally cached password was used.", "warning")
            else:
                flash("Supabase could not be reached, so sign-in is unavailable. "
                      "Check the internet connection.", "error")

        if signed_in:
            from flask import session
            session["user_id"] = user["id"]
            db.record_login(user["id"], ip_address=request.remote_addr)
            flash("Welcome back, {}.".format(user["full_name"] or user["username"]), "success")
            return redirect(request.args.get("next") or url_for("dashboard"))

    return render_template("login.html", supabase=supabase_auth.health())


@app.route("/logout")
def logout():
    from flask import session
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/account/change-password", methods=["GET", "POST"])
def change_password():
    user = auth.current_user()
    if not user:
        return redirect(url_for("login"))
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new1 = request.form.get("new_password", "")
        new2 = request.form.get("confirm_password", "")
        if not auth.verify_password(current, user["password_hash"]):
            flash("Current password is incorrect.", "error")
        elif len(new1) < 6:
            flash("New password must be at least 6 characters.", "error")
        elif new1 != new2:
            flash("New passwords do not match.", "error")
        else:
            db.set_password(user["id"], auth.hash_password(new1), must_change_password=False)
            flash("Password updated.", "success")
            return redirect(url_for("dashboard"))
    return render_template("change_password.html", forced=bool(user.get("must_change_password")))


# --------------------------------------------------------------------------
# Dashboard / departments / forms / registers
# --------------------------------------------------------------------------

@app.route("/")
@auth.login_required
def dashboard():
    user = auth.current_user()
    allowed = auth.allowed_depts_for_current_user()
    summary = db.dept_summary()
    urgent = [i for i in db.expiring_items(90) if i["rag"] == "RED" and i["dept"] in allowed]
    upcoming = [i for i in db.expiring_items(90) if i["rag"] == "AMBER" and i["dept"] in allowed]
    recent = [r for r in db.recent_activity(40) if r["dept"] in allowed][:15]
    total_records = sum(v["total"] for d, v in summary.items() if d in allowed)
    total_forms = sum(1 for f in FORMS if f["dept"] in allowed)

    today_iso = date.today().isoformat()

    active_headcount = db.count_where_in("HR-002", "status", ["Active"])
    active_clients = db.count_where_in("SAL-002", "status", ["Active"])
    open_transactions = db.count_where_in("TXN-001", "status", ["Open"])
    commission_paid = db.sum_field("TXN-004", "net_commission", "status", ["Paid"])
    open_requisitions = db.count_where_in("REC-001", "status", ["Open"])
    pipeline_total = db.count_records("REC-002")
    open_tickets = db.count_where_in("HLP-001", "status", ["Open", "In Progress"])
    approvals = db.pending_approvals(depts_allowed=allowed, limit=25)

    stat_cards = [
        {"label": "Active Employees", "value": active_headcount, "icon": "users", "tone": "blue"},
        {"label": "Active Clients", "value": active_clients, "icon": "user-check", "tone": "green"},
        {"label": "Open Transactions", "value": open_transactions, "icon": "credit-card", "tone": "blue"},
        {"label": "Commission Paid (AED)", "value": "{:,.0f}".format(commission_paid), "icon": "dollar-sign", "tone": "green"},
        {"label": "Open Requisitions", "value": open_requisitions, "icon": "briefcase", "tone": "amber" if open_requisitions else "neutral"},
        {"label": "Candidates in Pipeline", "value": pipeline_total, "icon": "user-plus", "tone": "blue"},
        {"label": "Open Support Tickets", "value": open_tickets, "icon": "help-circle", "tone": "amber" if open_tickets else "green"},
        {"label": "Pending Approvals", "value": len(approvals), "icon": "check-square", "tone": "red" if approvals else "green"},
    ]

    dept_bars = _bars(db.field_counts("HR-002", "department"))
    status_bars = _status_bars(db.field_counts("HR-002", "status"))

    present = db.count_where("ATT-001", [("date", "eq", today_iso), ("status", "in", ["Present"])])
    absent = db.count_where("ATT-001", [("date", "eq", today_iso), ("status", "in", ["Absent"])])
    late = db.count_where("ATT-001", [("date", "eq", today_iso), ("status", "in", ["Late"])])
    on_leave = db.count_where("ATT-001", [("date", "eq", today_iso), ("status", "in", ["On Leave"])])
    half_day = db.count_where("ATT-001", [("date", "eq", today_iso), ("status", "in", ["Half Day"])])
    attendance_mix = [m for m in [
        {"label": "Present", "count": present, "color": "var(--green)"},
        {"label": "Absent", "count": absent, "color": "var(--red)"},
        {"label": "Late", "count": late, "color": "var(--amber)"},
        {"label": "Half Day", "count": half_day, "color": "var(--blue)"},
        {"label": "On Leave", "count": on_leave, "color": "var(--grey)"},
    ] if m["count"]]
    attendance_total = sum(m["count"] for m in attendance_mix) or 1

    clock_rows = db.records_where_in("ATT-001", "date", [today_iso], limit=50, order_by="check_in DESC")
    applicant_rows = db.records_where_in("REC-002", "status", ["Applied", "Screening", "Interview"], limit=6)
    new_joiners = db.records_where_in("HR-002", "status", ["Active", "On Leave"], limit=6, order_by="id DESC")
    todos = db.list_todos(user["id"])
    sales_overview = db.sum_field_by_month("TXN-004", "net_commission", "payment_date", months=6)
    invoice_rows = db.records_where_in("FIN-006", "status", ["Pending"], limit=6)
    transaction_rows = db.records_where_in("TXN-001", "status", ["Open"], limit=8, order_by="id DESC")
    if not transaction_rows:
        transaction_rows = db.get_records("TXN-001", page=None)[0][:8]
    compliance_bars = _status_bars(db.field_counts("COR-003", "status"))
    meetings = db.list_meetings_upcoming(limit=6)
    birthdays = db.upcoming_birthdays("HR-002", "date_of_birth", "full_name", days_ahead=30)

    return render_template(
        "dashboard.html",
        summary=summary,
        urgent=urgent[:25],
        upcoming=upcoming[:25],
        recent=recent,
        total_records=total_records,
        total_forms=total_forms,
        FORMS_BY_CODE=FORMS_BY_CODE,
        stat_cards=stat_cards,
        dept_bars=dept_bars,
        status_bars=status_bars,
        attendance_mix=attendance_mix,
        attendance_total=attendance_total,
        clock_rows=clock_rows,
        applicant_rows=applicant_rows,
        new_joiners=new_joiners,
        todos=todos,
        sales_overview=sales_overview,
        invoice_rows=invoice_rows,
        transaction_rows=transaction_rows,
        compliance_bars=compliance_bars,
        meetings=meetings,
        birthdays=birthdays,
        approvals=approvals,
        today_iso=today_iso,
    )


@app.route("/me")
@auth.login_required
def employee_dashboard():
    user = auth.current_user()
    name = user.get("full_name") or user.get("username")

    emp_matches = db.records_where_in("HR-002", "full_name", [name], limit=1) if name else []
    emp = emp_matches[0] if emp_matches else None

    today_iso = date.today().isoformat()
    first_of_month = date.today().replace(day=1).isoformat()
    year_start = date.today().replace(month=1, day=1).isoformat()

    today_att = db.get_today_attendance(name, today_iso) if name else None

    my_leaves = db.records_where_in("HR-007", "employee_name", [name], limit=200) if name else []
    leave_pending = [r for r in my_leaves if (r.get("status") or "").lower() == "pending"]
    leave_approved_ytd = [r for r in my_leaves
                           if (r.get("status") or "").lower() == "approved" and (r.get("from_date") or "") >= year_start]
    leave_days_taken = sum(float(r.get("days") or 0) for r in leave_approved_ytd)
    leave_breakdown_map = {}
    for r in leave_approved_ytd:
        lt = r.get("leave_type") or "Other"
        leave_breakdown_map[lt] = leave_breakdown_map.get(lt, 0) + float(r.get("days") or 0)
    leave_breakdown = [{"label": k, "count": v, "color": _PALETTE[i % len(_PALETTE)]}
                        for i, (k, v) in enumerate(leave_breakdown_map.items())]

    skills = db.records_where_in("HR-017", "employee_name", [name], limit=20, order_by="proficiency_pct DESC") if name else []
    skill_bars = [{"label": s.get("skill_name") or "Skill", "value": float(s.get("proficiency_pct") or 0)} for s in skills]

    _RATING_SCORE = {"excellent": 100, "good": 75, "satisfactory": 50, "needs improvement": 25}
    reviews = db.records_where_in("HR-009", "employee_name", [name], limit=12, order_by="id ASC") if name else []
    performance_trend = [{"label": r.get("review_period") or r["doc_no"],
                           "total": _RATING_SCORE.get((r.get("rating") or "").lower(), 0)} for r in reviews]

    dept_code = (emp.get("department") or "").strip() if emp else None
    team_members = db.records_where_in("HR-002", "department", [dept_code], limit=8) if dept_code else []
    team_members = [m for m in team_members if (m.get("full_name") or "").strip().lower() != (name or "").strip().lower()]
    if dept_code:
        birthdays = db.upcoming_birthdays("HR-002", "date_of_birth", "full_name", days_ahead=30,
                                           extra_where=("department", [dept_code]))
    else:
        birthdays = db.upcoming_birthdays("HR-002", "date_of_birth", "full_name", days_ahead=30)

    my_transactions = db.records_where_in("TXN-001", "agent", [name], limit=6) if name else []
    my_compliance_items = db.records_where_in("COR-003", "responsible_person", [name], limit=6) if name else []

    my_requests = []
    for r in my_leaves[:8]:
        my_requests.append({"title": "Leave · {}".format(r.get("leave_type") or "—"),
                             "meta": "{} → {}".format(r.get("from_date") or "—", r.get("to_date") or "—"),
                             "status": r.get("status"), "form_code": "HR-007", "record_id": r["id"], "_id": r["id"]})
    for r in (db.records_where_in("PAY-003", "employee_name", [name], limit=5) if name else []):
        my_requests.append({"title": "Salary advance · AED {:,.0f}".format(r.get("amount") or 0),
                             "meta": r.get("requested_date") or "—", "status": r.get("status"),
                             "form_code": "PAY-003", "record_id": r["id"], "_id": r["id"]})
    my_requests.sort(key=lambda x: x["_id"], reverse=True)
    my_requests = my_requests[:8]

    hours_this_month = db.sum_field_since("ATT-001", "hours_worked", "date", first_of_month,
                                           where_field="employee_name", where_values=[name]) if name else 0

    stat_cards = [
        {"label": "Leave Days Taken (YTD)", "value": "{:.0f}".format(leave_days_taken), "icon": "calendar"},
        {"label": "Pending Requests", "value": len(leave_pending), "icon": "clock"},
        {"label": "Hours Worked This Month", "value": "{:.0f}".format(hours_this_month), "icon": "briefcase"},
        {"label": "Skills Tracked", "value": len(skills), "icon": "star"},
    ]

    meetings = db.list_meetings_upcoming(limit=6)
    todos = db.list_todos(user["id"])
    settings_data = db.get_settings()
    next_hol = db.next_holiday()

    photo = (emp.get("photo") if emp else None) or user.get("photo_path")

    return render_template(
        "employee_dashboard.html",
        emp=emp, photo=photo, today_att=today_att,
        leave_pending=leave_pending, leave_days_taken=leave_days_taken, leave_breakdown=leave_breakdown,
        skills=skills, skill_bars=skill_bars, performance_trend=performance_trend,
        team_members=team_members, birthdays=birthdays,
        my_transactions=my_transactions, my_compliance_items=my_compliance_items,
        my_requests=my_requests, stat_cards=stat_cards,
        meetings=meetings, todos=todos, settings=settings_data, next_holiday=next_hol,
        today_iso=today_iso,
    )


@app.route("/department/<dept_code>")
@auth.login_required
def department(dept_code):
    dept = DEPARTMENTS_BY_CODE.get(dept_code)
    if not dept:
        return "Department not found", 404
    _require_dept(dept_code)
    forms = forms_for_dept(dept_code)
    counts = db.all_counts()
    exp_items = [i for i in db.expiring_items(90) if i["dept"] == dept_code]
    red = [i for i in exp_items if i["rag"] == "RED"]
    amber = [i for i in exp_items if i["rag"] == "AMBER"]
    recent = [r for r in db.recent_activity(60) if r["dept"] == dept_code][:10]
    total = sum(counts.get(f["code"], 0) for f in forms)
    insight_panels = insights.build(dept_code)
    return render_template("department.html", dept=dept, forms=forms, counts=counts,
                            red=red, amber=amber, recent=recent, total=total,
                            insight_panels=insight_panels)


@app.route("/dashboards")
@auth.login_required
def dashboards_hub():
    allowed = auth.allowed_depts_for_current_user()
    visible = [d for d in insights.DASHBOARDS if d["dept"] is None or d["dept"] in allowed]
    return render_template("dashboards_hub.html", dashboards=visible)


@app.route("/dashboards/<key>")
@auth.login_required
def dashboard_view(key):
    d = insights.DASHBOARDS_BY_KEY.get(key)
    if not d:
        return "Dashboard not found", 404
    if key == "admin":
        return redirect(url_for("dashboard"))
    if key == "employee":
        return redirect(url_for("employee_dashboard"))
    _require_dept(d["dept"])
    dept = DEPARTMENTS_BY_CODE[d["dept"]]
    forms = forms_for_dept(d["dept"])
    counts = db.all_counts()
    exp_items = [i for i in db.expiring_items(90) if i["dept"] == d["dept"]]
    red = [i for i in exp_items if i["rag"] == "RED"]
    amber = [i for i in exp_items if i["rag"] == "AMBER"]
    recent = [r for r in db.recent_activity(60) if r["dept"] == d["dept"]][:10]
    total = sum(counts.get(f["code"], 0) for f in forms)
    panels = insights.dashboard_panels(key)
    return render_template("dashboard_view.html", dash=d, dept=dept, forms=forms, counts=counts,
                            red=red, amber=amber, recent=recent, total=total, panels=panels)


@app.route("/form/<form_code>", methods=["GET", "POST"])
@auth.login_required
def form_view(form_code):
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    dept = DEPARTMENTS_BY_CODE[form["dept"]]
    grouped = group_fields(form["fields"])

    photo_fields = [f["name"] for f in form["fields"] if f["type"] == "photo"]

    if request.method == "POST":
        data = {f["name"]: request.form.get(f["name"], "").strip() for f in form["fields"] if f["type"] != "photo"}
        for pf in photo_fields:
            data[pf] = ""
        data["status"] = request.form.get("status", "")
        data["notes"] = request.form.get("notes", "").strip()
        user = auth.current_user()
        created_by = user["full_name"] or user["username"]

        missing = [f["label"] for f in form["fields"] if f.get("required") and f["type"] != "photo" and not data.get(f["name"])]
        if missing:
            flash("Please fill in the required field(s): " + ", ".join(missing), "error")
            return render_template("form.html", form=form, dept=dept, values=data, edit=False, grouped=grouped)

        doc_no = db.insert_record(form_code, data, created_by=created_by)
        if photo_fields:
            record_id = db.get_id_by_doc_no(form_code, doc_no)
            for pf in photo_fields:
                file = request.files.get(pf)
                if file and file.filename and record_id:
                    relpath = db.save_uploaded_photo("records/{}".format(form_code), record_id, file)
                    if relpath:
                        db.set_field(form_code, record_id, pf, relpath)
        flash("Saved as {}".format(doc_no), "success")
        return redirect(url_for("register", form_code=form_code))

    return render_template("form.html", form=form, dept=dept, values={}, edit=False, grouped=grouped)


@app.route("/register/<form_code>")
@auth.login_required
def register(form_code):
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    dept = DEPARTMENTS_BY_CODE[form["dept"]]
    q = request.args.get("q", "").strip()
    sort = request.args.get("sort", "id")
    direction = request.args.get("dir", "desc")
    page = request.args.get("page", 1, type=int)
    page_size = 25
    rows, total = db.get_records(form_code, q=q or None, sort=sort, direction=direction,
                                  page=page, page_size=page_size)
    att_counts = db.attachment_counts_for(form_code, [r["id"] for r in rows])
    total_pages = max(1, (total + page_size - 1) // page_size)
    return render_template("register.html", form=form, dept=dept, rows=rows, q=q,
                            sort=sort, direction=direction, page=page, total_pages=total_pages,
                            total=total, att_counts=att_counts)


@app.route("/register/<form_code>/export.csv")
@auth.login_required
def export_csv(form_code):
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    csv_data = db.export_csv(form_code)
    filename = "{}_register.csv".format(form_code)
    return Response(csv_data, mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename={}".format(filename)})


@app.route("/record/<form_code>/<int:record_id>/download.<fmt>")
@auth.login_required
def record_download(form_code, record_id, fmt):
    """Download one record as CSV or JSON.

    Kept deliberately simple and dependency-free: a PDF is produced by the
    browser's own print-to-PDF from the record page, so this app never needs a
    PDF library installed on the user's machine.
    """
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    record = db.get_record(form_code, record_id)
    if not record:
        return "Record not found", 404

    labels = [("doc_no", "Doc No."), ("status", "Status")]
    labels += [(f["name"], f["label"]) for f in form["fields"]]
    labels += [("notes", "Notes"), ("created_by", "Created By"), ("created_at", "Created At")]

    base = "{}_{}".format(form_code, record.get("doc_no") or record_id).replace("/", "-")

    if fmt == "json":
        payload = {
            "form": {"code": form["code"], "title": form["title"], "department": form["dept"]},
            "record": {label: (record.get(name) or "") for name, label in labels},
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "exported_from": "DHARANI 360",
        }
        return Response(json.dumps(payload, indent=2, ensure_ascii=False),
                         mimetype="application/json",
                         headers={"Content-Disposition": 'attachment; filename="{}.json"'.format(base)})

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([label for _, label in labels])
        w.writerow([record.get(name) or "" for name, _ in labels])
        return Response(buf.getvalue(), mimetype="text/csv",
                         headers={"Content-Disposition": 'attachment; filename="{}.csv"'.format(base)})

    abort(404)


@app.route("/record/<form_code>/<int:record_id>")
@auth.login_required
def record_view(form_code, record_id):
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    dept = DEPARTMENTS_BY_CODE[form["dept"]]
    record = db.get_record(form_code, record_id)
    if not record:
        return "Record not found", 404
    grouped = group_fields(form["fields"])
    related = db.related_records(form_code, record_id)
    attachments = db.get_attachments(form_code, record_id)
    return render_template("record_view.html", form=form, dept=dept, record=record,
                            grouped=grouped, related=related, attachments=attachments,
                            allowed_ext=sorted(db.ALLOWED_ATTACHMENT_EXTENSIONS))


@app.route("/record/<form_code>/<int:record_id>/edit", methods=["GET", "POST"])
@auth.login_required
def record_edit(form_code, record_id):
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    dept = DEPARTMENTS_BY_CODE[form["dept"]]
    record = db.get_record(form_code, record_id)
    if not record:
        return "Record not found", 404
    grouped = group_fields(form["fields"])
    photo_fields = [f["name"] for f in form["fields"] if f["type"] == "photo"]

    if request.method == "POST":
        data = {f["name"]: request.form.get(f["name"], "").strip() for f in form["fields"] if f["type"] != "photo"}
        for pf in photo_fields:
            data[pf] = record.get(pf) or ""
        data["status"] = request.form.get("status", "")
        data["notes"] = request.form.get("notes", "").strip()
        db.update_record(form_code, record_id, data)
        for pf in photo_fields:
            file = request.files.get(pf)
            if file and file.filename:
                relpath = db.save_uploaded_photo("records/{}".format(form_code), record_id, file)
                if relpath:
                    db.set_field(form_code, record_id, pf, relpath)
        flash("{} updated".format(record["doc_no"]), "success")
        return redirect(url_for("record_view", form_code=form_code, record_id=record_id))

    return render_template("form.html", form=form, dept=dept, values=record, edit=True,
                            record=record, grouped=grouped)


@app.route("/record/<form_code>/<int:record_id>/delete", methods=["POST"])
@auth.login_required
def record_delete(form_code, record_id):
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    db.delete_record(form_code, record_id)
    flash("Record deleted", "success")
    return redirect(url_for("register", form_code=form_code))


# --------------------------------------------------------------------------
# Projects Kanban board
# --------------------------------------------------------------------------

@app.route("/projects/kanban")
@auth.login_required
def projects_kanban():
    _require_dept("PRJ")
    task_form = FORMS_BY_CODE["PRJ-002"]
    columns = task_form["status_options"]
    rows, _total = db.get_records("PRJ-002", page=None)
    board = {col: [r for r in rows if (r.get("status") or columns[0]) == col] for col in columns}
    return render_template("kanban.html", board=board, columns=columns, task_form=task_form)


@app.route("/projects/kanban/<int:record_id>/status", methods=["POST"])
@auth.login_required
def projects_kanban_status(record_id):
    _require_dept("PRJ")
    new_status = request.form.get("status", "")
    task_form = FORMS_BY_CODE["PRJ-002"]
    if new_status in task_form["status_options"]:
        db.set_field("PRJ-002", record_id, "status", new_status)
        flash("Task moved to {}".format(new_status), "success")
    return redirect(url_for("projects_kanban"))


# --------------------------------------------------------------------------
# Photos (user avatars + employee record photos)
# --------------------------------------------------------------------------

@app.route("/photos/<path:relpath>")
@auth.login_required
def photo_file(relpath):
    path = db.photo_disk_path(relpath)
    if not path or not os.path.exists(path):
        return "Not found", 404
    return send_file(path)


@app.route("/account/photo", methods=["POST"])
@auth.login_required
def account_photo():
    user = auth.current_user()
    file = request.files.get("photo")
    relpath, error = db.save_photo_checked("users", user["id"], file)
    if relpath:
        db.update_user_photo(user["id"], relpath)
        flash("Profile photo updated.", "success")
    else:
        flash(error or "That photo could not be saved.", "error")
    return redirect(request.form.get("next") or url_for("profile"))


@app.route("/profile", methods=["GET", "POST"])
@auth.login_required
def profile():
    """Everyone's own page. Any role can set their photo and display name.

    The role and the sign-in email are shown but not editable here - those
    decide what a person may reach, so they stay with an administrator on
    Users & Access. Letting people edit their own access would defeat the
    point of having roles at all.
    """
    user = auth.current_user()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        link, link_error = db.normalise_meeting_link(request.form.get("meeting_link", ""))
        if not full_name:
            flash("Your name cannot be empty.", "error")
        elif link_error:
            flash(link_error, "error")
        else:
            db.update_user(user["id"], full_name=full_name, meeting_link=link)
            flash("Profile updated.", "success")
        return redirect(url_for("profile"))

    staff = None
    if user["email"]:
        rows, _ = db.get_records("HR-002")
        staff = next((r for r in rows
                      if (r.get("email") or "").lower() == user["email"].lower()), None)
    return render_template("profile.html", u=user, staff=staff,
                            role_label=ROLES.get(user["role"], {}).get("label", user["role"]),
                            my_depts=depts_for_role(user["role"]))


# --------------------------------------------------------------------------
# Personal to-do list
# --------------------------------------------------------------------------

@app.route("/todo/add", methods=["POST"])
@auth.login_required
def todo_add():
    user = auth.current_user()
    text = request.form.get("text", "").strip()
    color = request.form.get("color", "blue")
    status = request.form.get("status", "To Do")
    if text:
        db.add_todo(user["id"], text, color, status)
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/todo/<int:todo_id>/toggle", methods=["POST"])
@auth.login_required
def todo_toggle(todo_id):
    user = auth.current_user()
    db.toggle_todo(todo_id, user["id"])
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/todo/<int:todo_id>/delete", methods=["POST"])
@auth.login_required
def todo_delete(todo_id):
    user = auth.current_user()
    db.delete_todo(todo_id, user["id"])
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/todo/<int:todo_id>/status", methods=["POST"])
@auth.login_required
def todo_status(todo_id):
    """Move a card between board lanes."""
    user = auth.current_user()
    db.set_todo_status(todo_id, user["id"], request.form.get("status", ""))
    return redirect(request.referrer or url_for("todos_page"))


@app.route("/todos")
@auth.login_required
def todos_page():
    """The board is the default view; ?view=list gives the old flat list."""
    user = auth.current_user()
    view = "list" if request.args.get("view") == "list" else "board"
    todos = db.list_todos(user["id"])
    board = {s: [t for t in todos if t["status"] == s] for s in db.TODO_STATUSES}
    return render_template("todos.html", todos=todos, board=board,
                            statuses=db.TODO_STATUSES, view=view)


# --------------------------------------------------------------------------
# Personal sticky notes ("Application" suite)
# --------------------------------------------------------------------------

@app.route("/notes")
@auth.login_required
def notes_page():
    user = auth.current_user()
    return render_template("notes.html", notes=db.list_notes(user["id"]))


@app.route("/notes/add", methods=["POST"])
@auth.login_required
def note_add():
    user = auth.current_user()
    text = request.form.get("text", "").strip()
    color = request.form.get("color", "blue")
    if text:
        db.add_note(user["id"], text, color)
    return redirect(request.referrer or url_for("notes_page"))


@app.route("/notes/<int:note_id>/delete", methods=["POST"])
@auth.login_required
def note_delete(note_id):
    user = auth.current_user()
    db.delete_note(note_id, user["id"])
    return redirect(request.referrer or url_for("notes_page"))


@app.route("/files")
@auth.login_required
def files_manager():
    allowed = auth.allowed_depts_for_current_user()
    files = db.list_all_attachments(depts_allowed=allowed, limit=300)
    library = db.list_library_files()
    total_bytes = sum((f.get("size_bytes") or 0) for f in files) + \
                  sum((f.get("size_bytes") or 0) for f in library)
    return render_template("files.html", files=files, library=library,
                            folders=db.LIBRARY_FOLDERS,
                            total_mb=total_bytes / (1024 * 1024),
                            allowed_ext=sorted(db.ALLOWED_ATTACHMENT_EXTENSIONS))


# --------------------------------------------------------------------------
# Meetings
# --------------------------------------------------------------------------

@app.route("/files/upload", methods=["POST"])
@auth.login_required
def library_upload():
    """Upload a file into the company library (not tied to any one record)."""
    user = auth.current_user()
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a file to upload first.", "error")
        return redirect(url_for("files_manager"))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in db.ALLOWED_ATTACHMENT_EXTENSIONS:
        flash("That file type isn't allowed. Allowed: {}.".format(
            ", ".join(sorted(db.ALLOWED_ATTACHMENT_EXTENSIONS))), "error")
        return redirect(url_for("files_manager"))

    data = file.read()
    if len(data) > db.MAX_ATTACHMENT_BYTES:
        flash("That file is larger than the 15MB limit.", "error")
        return redirect(url_for("files_manager"))

    db.add_library_file(
        original_name=file.filename,
        file_bytes=data,
        folder=request.form.get("folder", "General").strip() or "General",
        description=request.form.get("description", "").strip(),
        uploaded_by=user["full_name"] or user["username"],
    )
    flash("Uploaded {}.".format(file.filename), "success")
    return redirect(url_for("files_manager"))


@app.route("/files/library/<int:file_id>/download")
@auth.login_required
def library_download(file_id):
    rec = db.get_library_file(file_id)
    if not rec:
        abort(404)
    return send_file(db.library_file_path(rec), as_attachment=True,
                      download_name=rec["original_name"])


@app.route("/files/library/<int:file_id>/delete", methods=["POST"])
@auth.login_required
def library_delete(file_id):
    db.delete_library_file(file_id)
    flash("File removed from the library.", "success")
    return redirect(url_for("files_manager"))


# --------------------------------------------------------------------------
# Internal chat between colleagues.
# Messages are stored in this system's own database - nothing leaves the
# computer. It is not a live socket connection; the open thread refreshes
# itself every few seconds so a reply appears without reloading the page.
# --------------------------------------------------------------------------

@app.route("/chat")
@app.route("/chat/<username>")
@auth.login_required
def chat(username=None):
    me = auth.current_user()
    colleagues = [u for u in db.list_users()
                  if u["username"] != me["username"] and u.get("active", 1)]
    latest, unread = db.chat_overview(me["username"])

    for c in colleagues:
        last = latest.get(c["username"])
        c["last_message"] = last["body"] if last else ""
        c["last_at"] = last["created_at"] if last else ""
        c["last_from_me"] = bool(last and last["from_user"] == me["username"])
        c["unread"] = unread.get(c["username"], 0)
        c["call_count"] = db.count_calls_for(c["full_name"] or c["username"])
    colleagues.sort(key=lambda c: (c["last_at"] or ""), reverse=True)

    active = None
    thread = []
    if username == me["username"]:
        # You can't message yourself - fall back to the list rather than 404.
        return redirect(url_for("chat"))
    if username:
        active = next((c for c in colleagues if c["username"] == username), None)
        if not active:
            flash("That colleague doesn't have an active account.", "error")
            return redirect(url_for("chat"))
        thread = db.chat_thread(me["username"], username)
        db.mark_chat_read(me["username"], username)
        active["unread"] = 0
    elif colleagues:
        return redirect(url_for("chat", username=colleagues[0]["username"]))

    # The right-hand panel: what this conversation has actually produced.
    files, shared = [], []
    calls_with = []
    if active:
        for m in thread:
            if m.get("kind") == "file":
                files.append(m)
            elif m.get("kind") == "share":
                try:
                    m["share"] = json.loads(m["meta"] or "{}")
                except (TypeError, ValueError):
                    m["share"] = {}
                shared.append(m)
            elif m.get("kind") == "share":
                pass
        files.reverse()
        shared.reverse()
        db.expire_stale_calls()
        calls_with = db.recent_calls_with(me["username"], active["username"])

    for m in thread:
        if m.get("kind") == "share" and "share" not in m:
            try:
                m["share"] = json.loads(m["meta"] or "{}")
            except (TypeError, ValueError):
                m["share"] = {}

    return render_template("chat.html", colleagues=colleagues, active=active,
                            thread=thread, me=me, panel_files=files[:12],
                            panel_shared=shared[:12], panel_calls=calls_with)


@app.route("/chat/<username>/send", methods=["POST"])
@auth.login_required
def chat_send(username):
    me = auth.current_user()
    body = request.form.get("body", "").strip()
    target = db.get_user_by_username(username)
    if not target:
        abort(404)
    if body:
        db.send_chat(me["username"], username, body[:4000])
    return redirect(url_for("chat", username=username))


@app.route("/chat/<username>/messages.json")
@auth.login_required
def chat_messages_json(username):
    """Polled by the open thread so a colleague's reply appears on its own."""
    me = auth.current_user()
    if not db.get_user_by_username(username):
        abort(404)
    thread = db.chat_thread(me["username"], username)
    db.mark_chat_read(me["username"], username)
    out = []
    for m in thread:
        item = {"id": m["id"], "mine": m["from_user"] == me["username"],
                "body": m["body"], "at": (m["created_at"] or "")[11:16],
                "kind": m.get("kind") or "text"}
        if item["kind"] == "file":
            item["file"] = {"name": m["attach_name"],
                            "size": m["attach_size"] or 0,
                            "url": url_for("chat_file", message_id=m["id"])}
        elif item["kind"] in ("share", "call"):
            try:
                item["meta"] = json.loads(m["meta"] or "{}")
            except (TypeError, ValueError):
                item["meta"] = {}
        out.append(item)
    return {"messages": out}


@app.route("/meetings/add", methods=["POST"])
@auth.admin_required
def meeting_add():
    user = auth.current_user()
    db.add_meeting(
        request.form.get("title", "").strip(),
        request.form.get("category", "").strip(),
        request.form.get("meeting_date", "").strip(),
        request.form.get("start_time", "").strip(),
        request.form.get("end_time", "").strip(),
        request.form.get("link", "").strip(),
        request.form.get("attendees", "").strip(),
        user["full_name"] or user["username"],
    )
    flash("Meeting scheduled.", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/meetings/<int:meeting_id>/delete", methods=["POST"])
@auth.admin_required
def meeting_delete(meeting_id):
    db.delete_meeting(meeting_id)
    flash("Meeting removed.", "success")
    return redirect(request.referrer or url_for("dashboard"))


# --------------------------------------------------------------------------
# Attendance punch clock
# --------------------------------------------------------------------------

@app.route("/attendance/punch-in", methods=["POST"])
@auth.login_required
def attendance_punch_in():
    user = auth.current_user()
    name = user.get("full_name") or user.get("username")
    db.punch_in(name, created_by=name)
    flash("Punched in.", "success")
    return redirect(request.referrer or url_for("employee_dashboard"))


@app.route("/attendance/punch-out", methods=["POST"])
@auth.login_required
def attendance_punch_out():
    user = auth.current_user()
    name = user.get("full_name") or user.get("username")
    ok = db.punch_out(name)
    flash("Punched out." if ok else "You need to punch in first.", "success" if ok else "error")
    return redirect(request.referrer or url_for("employee_dashboard"))


# --------------------------------------------------------------------------
# Unified approvals
# --------------------------------------------------------------------------

@app.route("/approvals/<form_code>/<int:record_id>/<action>", methods=["POST"])
@auth.login_required
def approval_action(form_code, record_id, action):
    if action not in ("approve", "reject"):
        abort(404)
    form = FORMS_BY_CODE.get(form_code)
    if form:
        _require_dept(form["dept"])
    ok = db.resolve_approval(form_code, record_id, action)
    if ok:
        flash("Approved." if action == "approve" else "Rejected.", "success")
    else:
        flash("Could not process that request.", "error")
    return redirect(request.referrer or url_for("dashboard"))


# --------------------------------------------------------------------------
# Attachments
# --------------------------------------------------------------------------

@app.route("/record/<form_code>/<int:record_id>/attach", methods=["POST"])
@auth.login_required
def attach_file(form_code, record_id):
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        return "Form not found", 404
    _require_dept(form["dept"])
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choose a file first.", "error")
        return redirect(url_for("record_view", form_code=form_code, record_id=record_id))
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in db.ALLOWED_ATTACHMENT_EXTENSIONS:
        flash("File type not allowed. Allowed: {}".format(", ".join(sorted(db.ALLOWED_ATTACHMENT_EXTENSIONS))), "error")
        return redirect(url_for("record_view", form_code=form_code, record_id=record_id))
    file_bytes = file.read()
    if len(file_bytes) > db.MAX_ATTACHMENT_BYTES:
        flash("File is too large (max 15MB).", "error")
        return redirect(url_for("record_view", form_code=form_code, record_id=record_id))
    user = auth.current_user()
    db.add_attachment(form_code, record_id, file.filename, file_bytes,
                       uploaded_by=user["full_name"] or user["username"])
    flash("Attached {}".format(file.filename), "success")
    return redirect(url_for("record_view", form_code=form_code, record_id=record_id))


@app.route("/attachment/<int:attachment_id>/download")
@auth.login_required
def attachment_download(attachment_id):
    att = db.get_attachment(attachment_id)
    if not att:
        return "Not found", 404
    form = FORMS_BY_CODE.get(att["form_code"])
    if form:
        _require_dept(form["dept"])
    path = db.attachment_file_path(att)
    if not os.path.exists(path):
        return "File missing on disk", 404
    return send_file(path, as_attachment=True, download_name=att["original_name"])


@app.route("/attachment/<int:attachment_id>/delete", methods=["POST"])
@auth.login_required
def attachment_delete(attachment_id):
    att = db.get_attachment(attachment_id)
    if not att:
        return "Not found", 404
    form = FORMS_BY_CODE.get(att["form_code"])
    if form:
        _require_dept(form["dept"])
    db.delete_attachment(attachment_id)
    flash("Attachment removed.", "success")
    return redirect(url_for("record_view", form_code=att["form_code"], record_id=att["record_id"]))


# --------------------------------------------------------------------------
# Compliance calendar / search
# --------------------------------------------------------------------------

@app.route("/calendar")
@auth.login_required
def calendar():
    """Month grid combining three sources onto one calendar:
       meetings/events you schedule, statutory holidays, and every compliance
       deadline auto-derived from the registers."""
    today = date.today()
    try:
        year = request.args.get("year", today.year, type=int)
        month = request.args.get("month", today.month, type=int)
        if not (1 <= month <= 12) or not (1970 <= year <= 2200):
            raise ValueError
    except (TypeError, ValueError):
        year, month = today.year, today.month

    first = date(year, month, 1)
    last_day = cal_mod.monthrange(year, month)[1]
    last = date(year, month, last_day)

    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)

    allowed = auth.allowed_depts_for_current_user()

    # Deadlines: pull a wide horizon then keep the ones inside this month.
    deadlines = [i for i in db.expiring_items(horizon_days=3650) if i["dept"] in allowed]

    by_day = {}
    def put(day_iso, entry):
        by_day.setdefault(day_iso, []).append(entry)

    for m in db.list_meetings_between(first.isoformat(), last.isoformat()):
        put(m["meeting_date"], {
            "kind": "meeting", "id": m["id"], "title": m["title"],
            "meta": " ".join(x for x in [m.get("start_time") or "", m.get("category") or ""] if x).strip(),
            "url": None, "tone": (m.get("category") or "Meeting"),
            # carried so clicking the entry can open it straight into the editor
            "category": m.get("category") or "", "date": m.get("meeting_date") or "",
            "start_time": m.get("start_time") or "", "end_time": m.get("end_time") or "",
            "attendees": m.get("attendees") or "", "link": m.get("link") or "",
        })

    for h in db.list_holidays():
        if first.isoformat() <= (h.get("holiday_date") or "") <= last.isoformat():
            put(h["holiday_date"], {"kind": "holiday", "id": h["id"], "title": h["name"],
                                    "meta": "Holiday", "url": None, "tone": "Holiday"})

    for i in deadlines:
        exp = i.get("expiry_date") or ""
        if first.isoformat() <= exp <= last.isoformat():
            put(exp, {"kind": "deadline", "id": i["record_id"], "title": i["doc_no"],
                       "meta": i["form_title"], "tone": i["rag"],
                       "url": url_for("record_view", form_code=i["form_code"], record_id=i["record_id"])})

    # Build the 6x7 grid, Monday-first.
    weeks = cal_mod.Calendar(firstweekday=0).monthdatescalendar(year, month)
    grid = [[{"date": d, "iso": d.isoformat(), "in_month": d.month == month,
              "is_today": d == today, "entries": by_day.get(d.isoformat(), [])}
             for d in week] for week in weeks]

    agenda = sorted(
        [(d, e) for d, entries in by_day.items() for e in entries],
        key=lambda t: (t[0], 0 if t[1]["kind"] == "meeting" else 1)
    )

    upcoming = [i for i in deadlines if i["days_left"] >= 0][:12]

    return render_template("calendar.html",
                            grid=grid, agenda=agenda, upcoming=upcoming,
                            year=year, month=month,
                            month_name=cal_mod.month_name[month],
                            prev_y=prev_y, prev_m=prev_m, next_y=next_y, next_m=next_m,
                            today_iso=today.isoformat(),
                            weekday_names=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                            meeting_count=sum(1 for _, e in agenda if e["kind"] == "meeting"),
                            deadline_count=sum(1 for _, e in agenda if e["kind"] == "deadline"))


@app.route("/meetings/<int:meeting_id>/edit", methods=["POST"])
@auth.login_required
def meeting_edit(meeting_id):
    if not db.get_meeting(meeting_id):
        abort(404)
    db.update_meeting(
        meeting_id,
        request.form.get("title", "").strip(),
        request.form.get("category", "").strip(),
        request.form.get("meeting_date", "").strip(),
        request.form.get("start_time", "").strip(),
        request.form.get("end_time", "").strip(),
        request.form.get("link", "").strip(),
        request.form.get("attendees", "").strip(),
    )
    flash("Entry updated.", "success")
    return redirect(request.referrer or url_for("calendar"))


@app.route("/search")
@auth.login_required
def search():
    q = request.args.get("q", "").strip()
    allowed = auth.allowed_depts_for_current_user()
    results = [r for r in db.global_search(q) if r["dept"] in allowed] if q else []
    return render_template("search.html", q=q, results=results)


@app.route("/calls")
@auth.login_required
def calls():
    """Call history for the Call Log register (DR-SAL-009).

    This is a call *log*, not a dialer. The system runs offline on one computer
    with no telephony or video service attached, so it records calls that staff
    actually made or received rather than pretending to place them.
    """
    _require_dept("SAL")
    view = request.args.get("view", "all").lower()
    q = request.args.get("q", "").strip()
    rows, _ = db.get_records("SAL-009", q=q or None, sort="call_date", direction="desc")

    def is_video(r):
        return (r.get("call_type") or "") == "Video Call"

    counts = {
        "all": len(rows),
        "incoming": sum(1 for r in rows if r.get("call_direction") == "Incoming"),
        "outgoing": sum(1 for r in rows if r.get("call_direction") == "Outgoing"),
        "missed": sum(1 for r in rows if r.get("call_direction") == "Missed"),
        "video": sum(1 for r in rows if is_video(r)),
    }

    counts["voice"] = sum(1 for r in rows if not is_video(r))

    if view == "incoming":
        rows = [r for r in rows if r.get("call_direction") == "Incoming"]
    elif view == "outgoing":
        rows = [r for r in rows if r.get("call_direction") == "Outgoing"]
    elif view == "missed":
        rows = [r for r in rows if r.get("call_direction") == "Missed"]
    elif view == "video":
        rows = [r for r in rows if is_video(r)]
    elif view == "voice":
        rows = [r for r in rows if not is_video(r)]

    total_minutes = 0
    for r in rows:
        try:
            total_minutes += int(float(r.get("duration_minutes") or 0))
        except (TypeError, ValueError):
            pass

    today_iso = date.today().isoformat()
    follow_ups = [r for r in rows
                  if (r.get("follow_up_date") or "") and r["follow_up_date"] <= today_iso
                  and r.get("status") != "Closed"]

    return render_template("calls.html", rows=rows, counts=counts, view=view, q=q,
                            total_minutes=total_minutes, follow_ups=follow_ups,
                            form=FORMS_BY_CODE["SAL-009"], today=today_iso)


@app.route("/calls/<int:record_id>")
@auth.login_required
def call_detail(record_id):
    """Single-call screen: who, how long, what came of it, and what to do next."""
    _require_dept("SAL")
    call = db.get_record("SAL-009", record_id)
    if not call:
        abort(404)

    try:
        mins = float(call.get("duration_minutes") or 0)
    except (TypeError, ValueError):
        mins = 0.0
    total_seconds = int(round(mins * 60))
    duration_clock = "{:02d}:{:02d}".format(total_seconds // 60, total_seconds % 60)

    name = (call.get("contact_name") or "?").strip()
    initials = "".join(part[0] for part in name.split()[:2] if part).upper() or "?"

    # Everything else logged against the same person, newest first.
    same_contact = []
    if name:
        all_rows, _ = db.get_records("SAL-009", sort="call_date", direction="desc")
        same_contact = [r for r in all_rows
                        if (r.get("contact_name") or "").strip() == name and r["id"] != record_id][:8]

    return render_template("call_detail.html", call=call, initials=initials,
                            duration_clock=duration_clock, total_seconds=total_seconds,
                            same_contact=same_contact, today=date.today().isoformat())


@app.route("/calls/log", methods=["POST"])
@auth.login_required
def call_log_quick():
    """Quick-log a call from the Calls page without opening the full form."""
    _require_dept("SAL")
    user = auth.current_user()
    data = {
        "call_direction": request.form.get("call_direction", "Incoming").strip(),
        "call_type": request.form.get("call_type", "Voice Call").strip(),
        "contact_name": request.form.get("contact_name", "").strip(),
        "contact_number": request.form.get("contact_number", "").strip(),
        "call_date": request.form.get("call_date", "").strip() or date.today().isoformat(),
        "call_time": request.form.get("call_time", "").strip(),
        "duration_minutes": request.form.get("duration_minutes", "").strip(),
        "related_lead": request.form.get("related_lead", "").strip(),
        "outcome": request.form.get("outcome", "").strip(),
        "follow_up_date": request.form.get("follow_up_date", "").strip(),
        "summary": request.form.get("summary", "").strip(),
        "agent_name": user["full_name"] or user["username"],
        "status": "Follow-up Needed" if request.form.get("follow_up_date", "").strip() else "Logged",
    }
    if not data["contact_name"]:
        flash("A contact name is needed to log the call.", "error")
        return redirect(url_for("calls"))

    db.insert_record("SAL-009", data, created_by=user["full_name"] or user["username"])
    flash("Call logged for {}.".format(data["contact_name"]), "success")
    return redirect(url_for("calls", view=request.form.get("return_view", "all")))



# ============================================================================
#  CALLING, CHAT FILES AND SHARING
#  --------------------------------------------------------------------------
#  Three jobs that all come down to the same thing: moving one fact from the
#  person who has it to the person who needs it, and leaving a record behind.
#
#    * a call happens in a private room and writes itself into SAL-009
#    * a file dropped into chat is stored under instance/chatfiles
#    * a share puts a record into a colleague's conversation and their bell
#
#  Everything except the video room itself works with no internet connection.
# ============================================================================

# The video call itself happens in whichever provider the company is allowed
# to use - Google Meet, Zoom, Teams, Webex. DHARANI 360 does not host the
# video; it rings the person, hands out the link, times the call and writes it
# into the register. That split matters in the UAE, where VoIP is restricted
# to approved providers, so embedding one fixed service would simply not
# connect.

_PROVIDER_NAMES = {
    "meet.google.com": "Google Meet",
    "zoom.us": "Zoom",
    "teams.microsoft.com": "Microsoft Teams",
    "teams.live.com": "Microsoft Teams",
    "webex.com": "Webex",
    "whereby.com": "Whereby",
    "meet.jit.si": "Jitsi Meet",
}


def _provider_name(url):
    if not url:
        return ""
    host = urlparse(url).hostname or ""
    host = host.lower()
    for known, label in _PROVIDER_NAMES.items():
        if host == known or host.endswith("." + known):
            return label
    return "the meeting"


def _meeting_url_for(user, override=None):
    """Which room this call happens in: a one-off link if one was typed,
    otherwise the caller's own saved room. Returns (url, error)."""
    if override:
        url, err = db.normalise_meeting_link(override)
        if err:
            return None, err
        if url:
            return url, None
    saved = (user.get("meeting_link") or "").strip()
    if saved:
        return saved, None
    return None, ("Add your meeting room link on your profile first - your Google Meet, "
                  "Zoom, Teams or Webex address. DHARANI 360 rings the person and logs "
                  "the call; the video happens in your own meeting room.")


def _abs(path):
    """Absolute URL for a path on this server - what goes in a QR or an email."""
    return urljoin(request.url_root, path.lstrip("/"))


def _display_name(user):
    return (user.get("full_name") or user.get("username") or "").strip()


def _share_subject(kind, form_code=None, record_id=None):
    """Resolve what is being shared into a title, a line of detail and a link.

    Returns None when the thing does not exist or the person may not see it,
    so one function guards every share route.
    """
    if kind == "record":
        form = FORMS_BY_CODE.get(form_code)
        if not form:
            return None
        if not can_access_dept(auth.current_user()["role"], form["dept"]):
            return None
        rec = db.get_record(form_code, record_id)
        if not rec:
            return None
        dept = DEPARTMENTS_BY_CODE.get(form["dept"], {})
        bits = []
        for f in form["fields"][:3]:
            v = rec.get(f["name"])
            if v not in (None, ""):
                bits.append("{}: {}".format(f["label"], v))
        return {
            "kind": "record", "form_code": form_code, "record_id": record_id,
            "title": "{} - {}".format(rec.get("doc_no") or form["code"], form["title"]),
            "detail": " | ".join(bits)[:190] or dept.get("name", ""),
            "badge": "DR-" + form["code"], "dept": form["dept"],
            "status": rec.get("status") or "",
            "url": url_for("record_view", form_code=form_code, record_id=record_id),
        }
    if kind == "register":
        form = FORMS_BY_CODE.get(form_code)
        if not form:
            return None
        if not can_access_dept(auth.current_user()["role"], form["dept"]):
            return None
        rows, total = db.get_records(form_code)
        return {
            "kind": "register", "form_code": form_code, "record_id": None,
            "title": form["title"],
            "detail": "{} record{} in this register".format(total, "" if total == 1 else "s"),
            "badge": "DR-" + form["code"], "dept": form["dept"], "status": "",
            "url": url_for("register", form_code=form_code),
        }
    return None


@app.route("/qr.svg")
@auth.login_required
def qr_svg():
    """A QR code for one of this system's own pages.

    Only addresses on this server are encoded. That is deliberate: it keeps
    DHARANI 360 from being used to dress up somebody else's link as ours.
    """
    target = request.args.get("d", "").strip()
    if not target:
        abort(400)
    if not target.startswith(("/", request.url_root)):
        abort(400)
    if target.startswith("/"):
        target = _abs(target)
    try:
        svg = qrgen.qr_svg(target, scale=int(request.args.get("s", 6)),
                            dark="#0b2b33", light="#ffffff",
                            title="Opens this page in DHARANI 360")
    except qrgen.QRError:
        abort(400)
    resp = make_response(svg)
    resp.headers["Content-Type"] = "image/svg+xml"
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@app.route("/share", methods=["POST"])
@auth.login_required
def share_send():
    """Hand a record or a register to one or more colleagues.

    It lands in their conversation as a card and, because it is an unread
    message, on their notification bell. Nothing leaves this system.
    """
    me = auth.current_user()
    kind = request.form.get("kind", "record")
    form_code = request.form.get("form_code") or None
    record_id = request.form.get("record_id", type=int)
    note = (request.form.get("note") or "").strip()[:500]
    targets = [t for t in request.form.getlist("to") if t and t != me["username"]]
    back = request.form.get("next") or request.referrer or url_for("dashboard")

    subject = _share_subject(kind, form_code, record_id)
    if not subject:
        flash("That item could not be shared - it may have been deleted.", "error")
        return redirect(back)
    if not targets:
        flash("Choose at least one colleague to share with.", "error")
        return redirect(back)

    allowed = {u["username"] for u in db.list_users() if u.get("active", 1)}
    sent = []
    for username in targets:
        if username not in allowed:
            continue
        target = db.get_user_by_username(username)
        if target and not can_access_dept(target["role"], subject.get("dept") or ""):
            flash("{} does not have access to {} - not shared with them."
                  .format(target["full_name"] or username,
                          DEPARTMENTS_BY_CODE.get(subject.get("dept"), {}).get("name", "that department")),
                  "warning")
            continue
        db.send_chat(me["username"], username, note or subject["title"],
                     kind="share", meta=subject)
        sent.append(target["full_name"] if target else username)

    if sent:
        flash("Shared with {}. It is in their chat now.".format(", ".join(sent)), "success")
    return redirect(back)


@app.route("/chat/<username>/attach", methods=["POST"])
@auth.login_required
def chat_attach(username):
    """Send a document or a photo inside a conversation."""
    me = auth.current_user()
    if not db.get_user_by_username(username) or username == me["username"]:
        abort(404)
    fs = request.files.get("file")
    if not fs:
        flash("No file was chosen.", "error")
        return redirect(url_for("chat", username=username))
    _mid, err = db.send_chat_file(me["username"], username, fs,
                                  caption=(request.form.get("caption") or "").strip()[:300])
    if err:
        flash(err, "error")
    return redirect(url_for("chat", username=username))


@app.route("/chat/file/<int:message_id>")
@auth.login_required
def chat_file(message_id):
    """Download a chat attachment - only the two people in the conversation."""
    me = auth.current_user()["username"]
    msg = db.get_chat_message(message_id)
    if not msg or msg["kind"] != "file":
        abort(404)
    if me not in (msg["from_user"], msg["to_user"]):
        abort(403)
    path = db.chat_file_path(msg)
    if not path:
        abort(404)
    return send_file(path, as_attachment=True,
                     download_name=msg["attach_name"] or "attachment")


# ------------------------------------------------------------------- calls --

def _call_can_see(call, user):
    return user["username"] in (call["started_by"], call["other_user"] or "")


def _log_call_to_register(call, logged_by):
    """Write a finished call into DR-SAL-009 so it joins the permanent history."""
    if call.get("record_id"):
        return call["record_id"]
    minutes = round((call.get("duration_seconds") or 0) / 60.0, 1)
    started = call.get("started_at") or ""
    other = call.get("contact_name")
    if not other and call.get("other_user"):
        u = db.get_user_by_username(call["other_user"])
        other = (u["full_name"] if u else call["other_user"])
    direction = "Outgoing" if call["started_by"] == logged_by else "Incoming"
    if call.get("status") == db.CALL_STATUS_MISSED:
        direction = "Missed"
    data = {
        "call_direction": direction,
        "call_type": "Video Call" if call.get("mode") != "voice" else "Voice Call",
        "contact_name": other or "Unknown",
        "contact_number": call.get("contact_number") or "",
        "call_date": (started[:10] or date.today().isoformat()),
        "call_time": started[11:16],
        "duration_minutes": minutes,
        "outcome": call.get("outcome") or ("No answer" if call.get("status") == db.CALL_STATUS_MISSED
                                           else "Completed"),
        "summary": call.get("subject") or "",
        "agent_name": logged_by,
        "status": "Logged",
        "notes": "[in-app call]",
    }
    try:
        doc_no = db.insert_record("SAL-009", data, created_by=logged_by)
    except Exception:
        return None
    # insert_record hands back the document number; the row id is what the
    # call-detail URL needs.
    rid = db.record_id_for_doc("SAL-009", doc_no)
    if rid:
        db.attach_call_record(call["id"], rid)
    return rid


@app.route("/call/start/<username>", methods=["POST"])
@auth.login_required
def call_start(username):
    """Ring a colleague. Creates the room and drops a card in their chat."""
    me = auth.current_user()
    target = db.get_user_by_username(username)
    if not target or username == me["username"] or not target.get("active", 1):
        abort(404)
    db.expire_stale_calls()
    mode = "voice" if request.form.get("mode") == "voice" else "video"

    meeting_url, err = _meeting_url_for(me, request.form.get("meeting_link"))
    if err:
        flash(err, "error")
        return redirect(url_for("profile"))

    call = db.start_call(me["username"], other_user=username, mode=mode,
                         subject=(request.form.get("subject") or "").strip()[:160],
                         meeting_url=meeting_url)
    db.send_chat(me["username"], username,
                 "{} call started".format("Video" if mode == "video" else "Voice"),
                 kind="call", meta={"call_id": call["id"], "mode": mode,
                                    "status": "ringing"})
    return redirect(url_for("call_room", call_id=call["id"]))


@app.route("/call/quick", methods=["POST"])
@auth.login_required
def call_quick():
    """Open a room for somebody outside the company - a client, an owner, a
    lawyer. They join with the guest link; no account, nothing to install."""
    me = auth.current_user()
    name = (request.form.get("contact_name") or "").strip()
    if not name:
        flash("Who is the call with? Add a name so it can be logged.", "error")
        return redirect(url_for("calls"))
    meeting_url, err = _meeting_url_for(me, request.form.get("meeting_link"))
    if err:
        flash(err, "error")
        return redirect(url_for("profile"))
    call = db.start_call(me["username"], contact_name=name,
                         contact_number=(request.form.get("contact_number") or "").strip(),
                         mode="voice" if request.form.get("mode") == "voice" else "video",
                         subject=(request.form.get("subject") or "").strip()[:160],
                         meeting_url=meeting_url)
    return redirect(url_for("call_room", call_id=call["id"]))


@app.route("/call/<int:call_id>")
@auth.login_required
def call_room(call_id):
    """The call screen itself."""
    me = auth.current_user()
    call = db.get_call(call_id)
    if not call:
        abort(404)
    if not _call_can_see(call, me):
        abort(403)
    if call["other_user"] == me["username"]:
        call = db.answer_call(call_id)

    other = None
    if call["other_user"]:
        other = db.get_user_by_username(
            call["other_user"] if call["started_by"] == me["username"] else call["started_by"])
    guest_link = _abs(url_for("call_guest", token=call["guest_token"]))
    history = db.recent_calls_with(me["username"], call["other_user"] or "") if call["other_user"] else []

    return render_template("call_room.html", call=call, other=other, me=me,
                            guest_link=guest_link, meeting_url=call.get("meeting_url") or "",
                            provider=_provider_name(call.get("meeting_url")),
                            history=history)


@app.route("/call/<int:call_id>/end", methods=["POST"])
@auth.login_required
def call_end(call_id):
    """Hang up and write the call into the register. Called by the page when
    the room closes, and by the Leave button, so a closed tab still logs."""
    me = auth.current_user()
    call = db.get_call(call_id)
    if not call:
        abort(404)
    if not _call_can_see(call, me):
        abort(403)
    seconds = request.form.get("seconds", type=int)
    if seconds is None:
        seconds = (request.get_json(silent=True) or {}).get("seconds")
    ended = db.end_call(call_id, seconds=seconds,
                        outcome=(request.form.get("outcome") or "").strip()[:200])
    rid = _log_call_to_register(ended, _display_name(me))
    if request.form.get("quiet") or request.headers.get("X-Requested-With") == "beacon":
        return {"ok": True, "record_id": rid}
    if rid:
        flash("Call ended and logged to the Call Log.", "success")
    return redirect(url_for("call_detail", record_id=rid) if rid else url_for("calls"))


@app.route("/call/<int:call_id>/decline", methods=["POST"])
@auth.login_required
def call_decline(call_id):
    me = auth.current_user()
    call = db.get_call(call_id)
    if not call or not _call_can_see(call, me):
        abort(404)
    ended = db.end_call(call_id, seconds=0, status=db.CALL_STATUS_MISSED,
                        outcome="Declined")
    _log_call_to_register(ended, _display_name(me))
    return {"ok": True}


@app.route("/call/incoming.json")
@auth.login_required
def call_incoming():
    """Polled by every page so a call rings wherever the person is."""
    me = auth.current_user()
    db.expire_stale_calls()
    out = []
    for c in db.incoming_calls_for(me["username"]):
        caller = db.get_user_by_username(c["started_by"])
        out.append({
            "id": c["id"], "mode": c["mode"],
            "from": (caller["full_name"] if caller else c["started_by"]),
            "role": (caller["role"] if caller else ""),
            "url": url_for("call_room", call_id=c["id"]),
            "decline": url_for("call_decline", call_id=c["id"]),
        })
    return {"calls": out}


@app.route("/call/guest/<token>")
def call_guest(token):
    """The link handed to somebody outside the company. No sign-in: holding
    the link is the permission, which is why the token is long and random."""
    call = db.get_call_by_token(token)
    if not call:
        return render_template("error.html", code=404,
                                message="That call link is not valid. Ask for a new one."), 404
    if call["status"] == db.CALL_STATUS_ENDED:
        return render_template("error.html", code=410,
                                message="That call has already finished."), 410
    host = db.get_user_by_username(call["started_by"])
    return render_template("call_guest.html", call=call,
                            meeting_url=call.get("meeting_url") or "",
                            provider=_provider_name(call.get("meeting_url")),
                            host_name=(host["full_name"] if host else "DHARANI 360"))


# --------------------------------------------------------------------- PDF --

def _pdf_response(doc, filename):
    resp = make_response(doc.bytes())
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = 'attachment; filename="{}"'.format(filename)
    return resp


@app.route("/record/<form_code>/<int:record_id>/sheet.pdf")
@auth.login_required
def record_pdf(form_code, record_id):
    """One record as a branded PDF - the thing you send to a client or a bank."""
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        abort(404)
    _require_dept(form["dept"])
    rec = db.get_record(form_code, record_id)
    if not rec:
        abort(404)
    me = auth.current_user()
    dept = DEPARTMENTS_BY_CODE.get(form["dept"], {})

    doc = pdfout.Document(
        form["title"], "DR-{} / {}".format(form["code"], dept.get("name", "")),
        footer="DHARANI 360 - shared by {} on {}".format(
            _display_name(me), date.today().strftime("%d %b %Y")))
    meta = [("Document no", rec.get("doc_no") or "-"), ("Status", rec.get("status") or "-")]
    if form.get("expiry_field"):
        meta.append(("Expires", rec.get(form["expiry_field"]) or "-"))
    meta.append(("Recorded by", rec.get("created_by") or "-"))
    doc.doc_head(meta)

    doc.heading("Record details")
    doc.fields([(f["label"], rec.get(f["name"])) for f in form["fields"]
                if f["name"] != "notes"], columns=2)

    if rec.get("notes"):
        doc.heading("Notes")
        doc.paragraph(rec["notes"])

    atts = db.get_attachments(form_code, record_id)
    if atts:
        doc.heading("Attached documents")
        doc.table(["File", "Size", "Attached by", "When"],
                  [[a["original_name"], "{:.0f} KB".format((a["size_bytes"] or 0) / 1024.0),
                    a["uploaded_by"] or "-", (a["uploaded_at"] or "")[:10]] for a in atts],
                  widths=[0.44, 0.14, 0.24, 0.18])

    doc.space(4)
    doc.callout("This is a copy",
                "The live record is the one inside DHARANI 360. If this sheet and the system "
                "disagree, the system is right. Printed {}.".format(
                    datetime.now().strftime("%d %b %Y at %H:%M")))
    doc.qr(qrgen.matrix(_abs(url_for("record_view", form_code=form_code, record_id=record_id))),
           "Scan to open this record")
    return _pdf_response(doc, "{}.pdf".format((rec.get("doc_no") or form["code"]).replace("/", "-")))


@app.route("/register/<form_code>/export.pdf")
@auth.login_required
def register_pdf(form_code):
    """A whole register as a PDF table - for a meeting, an audit or an email."""
    form = FORMS_BY_CODE.get(form_code)
    if not form:
        abort(404)
    _require_dept(form["dept"])
    q = request.args.get("q", "").strip()
    rows, total = db.get_records(form_code, q=q or None)
    dept = DEPARTMENTS_BY_CODE.get(form["dept"], {})
    me = auth.current_user()

    doc = pdfout.Document(
        form["title"], "DR-{} / {}".format(form["code"], dept.get("name", "")),
        footer="DHARANI 360 - exported by {} on {}".format(
            _display_name(me), date.today().strftime("%d %b %Y")))
    doc.doc_head([("Records", str(total)),
                  ("Filter", q or "none"),
                  ("Exported", date.today().strftime("%d %b %Y"))])

    cols = [{"label": "Doc no", "name": "doc_no"}] + form["fields"][:4] + [
        {"label": "Status", "name": "status"}]
    body = form["fields"][:4]
    widths = [0.24] + [0.63 / max(1, len(body))] * len(body) + [0.13]
    doc.heading("Register")
    doc.table([c["label"] for c in cols],
              [[r.get(c["name"]) for c in cols] for r in rows],
              widths=widths[:len(cols)], max_rows=400)
    if total > 400:
        doc.paragraph("Showing the first 400 of {} records. Narrow the search to export "
                      "a smaller set.".format(total), color=pdfout.MUTED)
    doc.space(4)
    doc.qr(qrgen.matrix(_abs(url_for("register", form_code=form_code))),
           "Scan to open the live register")
    return _pdf_response(doc, "{}-register.pdf".format(form["code"]))


@app.route("/regulations")
@auth.login_required
def regulations():
    """Company Rules & Regulations library.

    Two distinct things are shown side by side and must never be confused:
      * "rules"       - DHARANI 360's own internal operating rules for the
                        department. These are company policy, set by us.
      * "regulations" - external UAE/Dubai law the department touches. These
                        are reference pointers only, never legal advice.
    """
    allowed = auth.allowed_depts_for_current_user()
    accessible_depts = [d for d in DEPARTMENTS if d["code"] in allowed]

    # One department at a time. Stacking all seventeen produced a page nobody
    # read to the bottom of; the rail on the left is how you move between them.
    focus = request.args.get("dept", "").strip().upper()
    if focus not in allowed:
        focus = accessible_depts[0]["code"] if accessible_depts else ""
    visible_depts = [d for d in accessible_depts if d["code"] == focus]
    focus_dept = visible_depts[0] if visible_depts else None

    # The rail always lists every department the user can reach, even when the
    # page itself is focused on one. Filtering it to the focused department
    # left the reader with a one-item navigation and no way across.
    nav_depts = [{"code": d["code"], "name": d["name"], "color": d["color"],
                   "total": regulations_data.counts_for_dept(d["code"])["total"]}
                  for d in accessible_depts]

    codes = [d["code"] for d in visible_depts]
    total_rules = sum(len(d.get("rules") or []) for d in visible_depts)
    total_laws = sum(len(d.get("regulations") or []) for d in visible_depts)

    # The researched, cited UAE/Dubai obligation set (regulations_data.py).
    # Authorities are counted across both the obligation set and the older
    # framework pointers so the hero number reflects everything on the page.
    obligations = {c: regulations_data.for_dept(c) for c in codes}
    oblig_counts = {c: regulations_data.counts_for_dept(c) for c in codes}
    dept_authorities = {c: regulations_data.distinct_authorities([c]) for c in codes}
    dept_marks = {c: regulations_data.authorities_for_dept(c) for c in codes}
    severity_totals = {"critical": 0, "high": 0, "medium": 0}
    for c in codes:
        for k in severity_totals:
            severity_totals[k] += oblig_counts[c].get(k, 0)
    authorities = sorted(
        set(regulations_data.all_authorities(codes))
        | {r["authority"] for d in visible_depts for r in (d.get("regulations") or [])}
    )
    return render_template("regulations.html", visible_depts=visible_depts,
                            nav_depts=nav_depts, focus_dept=focus_dept,
                            library_total=regulations_data.total_count(
                                [d["code"] for d in accessible_depts]),
                            total_rules=total_rules, total_laws=total_laws,
                            authorities=authorities, focus=focus,
                            obligations=obligations, oblig_counts=oblig_counts,
                            dept_authorities=dept_authorities, dept_marks=dept_marks,
                            severity_totals=severity_totals,
                            total_obligations=regulations_data.total_count(codes),
                            total_critical=regulations_data.critical_count(codes),
                            SEVERITY_TONE=regulations_data.SEVERITY_TONE,
                            SEVERITY_LABEL=regulations_data.SEVERITY_LABEL)


@app.route("/documentation")
@auth.login_required
def documentation():
    allowed = auth.allowed_depts_for_current_user()
    visible_depts = [d for d in DEPARTMENTS if d["code"] in allowed]
    return render_template("documentation.html", visible_depts=visible_depts, forms_for_dept=forms_for_dept)


# --------------------------------------------------------------------------
# AI Insights Center - rule-based analytics over real data.
# This is NOT a chatbot and does not call any external AI/LLM service; it is
# a set of plain if/threshold rules over the company's own registers, kept
# separate from any one department so leadership gets one cross-cutting view.
# --------------------------------------------------------------------------

@app.route("/insights-center")
@auth.login_required
def insights_center():
    user = auth.current_user()
    if not (is_admin_role(user["role"]) or user["role"] == "Manager"):
        abort(403)
    allowed = auth.allowed_depts_for_current_user()
    today_iso = date.today().isoformat()

    at_risk = [i for i in db.expiring_items(30) if i["dept"] in allowed]
    red_items = [i for i in at_risk if i["rag"] == "RED"]
    amber_items = [i for i in at_risk if i["rag"] == "AMBER"]

    approvals = db.pending_approvals(depts_allowed=allowed, limit=100)

    open_tickets = db.count_where_in("HLP-001", "status", ["Open", "In Progress"]) if "HLP" in allowed else 0
    critical_tickets = db.count_where_in("HLP-001", "priority", ["Critical"]) if "HLP" in allowed else 0

    needs_improvement = db.count_where_in("HR-009", "rating", ["Needs Improvement"]) if "HR" in allowed else 0
    grievances_open = db.count_where_in("HR-012", "status", ["Open", "Under Investigation", "New"]) if "HR" in allowed else 0
    recruitment_bars = _bars(db.field_counts("REC-002", "status")) if "REC" in allowed else []

    pending_payment_value = db.sum_field("FIN-004", "amount", "status", ["Pending"]) if "FIN" in allowed else 0
    pending_invoices = db.count_where_in("FIN-006", "status", ["Pending"]) if "FIN" in allowed else 0

    blocked_tasks = db.count_where_in("PRJ-002", "status", ["Blocked"]) if "PRJ" in allowed else 0
    overdue_tasks = db.count_where("PRJ-002", [("due_date", "lt", today_iso), ("status", "not_in", ["Done"])]) if "PRJ" in allowed else 0
    open_projects = db.count_where_in("PRJ-001", "status", ["Planning", "In Progress"]) if "PRJ" in allowed else 0

    kpis = [
        {"label": "Compliance items overdue/expiring ≤30d", "value": len(at_risk), "tone": "red" if red_items else ("amber" if amber_items else "green")},
        {"label": "Pending approvals company-wide", "value": len(approvals), "tone": "red" if approvals else "green"},
        {"label": "Open support tickets", "value": open_tickets, "tone": "amber" if open_tickets else "green"},
        {"label": "Open HR grievances", "value": grievances_open, "tone": "red" if grievances_open else "green"},
        {"label": "Overdue project tasks", "value": overdue_tasks, "tone": "red" if overdue_tasks else "green"},
        {"label": "Pending payment approvals (AED)", "value": "{:,.0f}".format(pending_payment_value), "tone": "amber" if pending_payment_value else "green"},
    ]

    suggestions = []
    if red_items:
        suggestions.append("{} compliance item(s) are already overdue or expiring within 30 days — review the Compliance Calendar first.".format(len(red_items)))
    if grievances_open:
        suggestions.append("{} employee grievance(s) are still open — these typically need the fastest turnaround of any HR item.".format(grievances_open))
    if needs_improvement:
        suggestions.append("{} performance review(s) are rated 'Needs Improvement' — consider scheduling a Performance Improvement Plan (HR-010).".format(needs_improvement))
    if critical_tickets:
        suggestions.append("{} support ticket(s) are marked Critical priority and still open.".format(critical_tickets))
    if overdue_tasks or blocked_tasks:
        suggestions.append("{} project task(s) are overdue and {} are blocked — check the Projects Kanban board.".format(overdue_tasks, blocked_tasks))
    if pending_invoices:
        suggestions.append("{} vendor invoice(s) are awaiting verification in Finance.".format(pending_invoices))
    if not suggestions:
        suggestions.append("No urgent flags right now across the departments you can see — everything is within normal thresholds.")

    return render_template(
        "insights_center.html",
        kpis=kpis, at_risk=at_risk[:15], approvals=approvals[:10],
        recruitment_bars=recruitment_bars, suggestions=suggestions,
        open_projects=open_projects, blocked_tasks=blocked_tasks, overdue_tasks=overdue_tasks,
    )


# --------------------------------------------------------------------------
# Users & Settings (administrators only)
# --------------------------------------------------------------------------

@app.route("/users", methods=["GET", "POST"])
@auth.admin_required
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "")
        password = request.form.get("password", "")
        if not username or not password or role not in ROLES:
            flash("Please fill in username, password and a valid role.", "error")
        elif db.get_user_by_username(username):
            flash("That username is already taken.", "error")
        elif email and db.get_user_by_email(email):
            flash("That email address is already used by another account.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            user_id = db.create_user(username, auth.hash_password(password),
                                      full_name, role, must_change_password=True)
            if email:
                db.set_user_email(user_id, email)
            # Sign-in is by work email, so an account without one - or with one
            # that is not on the allowlist - cannot get in. Say so now rather
            # than letting the person discover it at the login screen.
            if not email:
                flash("User {} created, but with no email address they cannot sign in. "
                      "Add one below.".format(username), "warning")
            elif not supabase_auth.is_allowed(email):
                flash("User {} created. {} is not on the sign-in allowlist yet, so they "
                      "cannot sign in until it is added to ALLOWED_EMAILS in "
                      "supabase_auth.py.".format(username, email), "warning")
            else:
                flash("User {} created.".format(username), "success")
        return redirect(url_for("users"))
    return render_template("users.html", user_list=db.list_users(),
                            ROLES=ROLES, ROLE_NAMES=ROLE_NAMES,
                            can_sign_in=_can_sign_in)


def _can_sign_in(user):
    """Sign-in needs a work email that is on the allowlist. An account
    missing either is inert, so the page says so instead of leaving the
    person to find out at the login screen."""
    email = (user["email"] or "").strip()
    return bool(email) and supabase_auth.is_allowed(email)


@app.route("/users/<int:user_id>/update", methods=["POST"])
@auth.admin_required
def user_update(user_id):
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "")
    active = request.form.get("active") == "on"

    me = auth.current_user()
    target = db.get_user(user_id)
    if target is None:
        flash("That user no longer exists.", "error")
        return redirect(url_for("users"))

    # Never let the last way back in be closed by accident.
    losing_admin = (is_admin_role(target["role"]) and
                    (not active or not is_admin_role(role if role in ROLES else target["role"])))
    if losing_admin and _other_active_admins(user_id) == 0:
        flash("This is the only administrator left. Give somebody else an "
              "administrator role first, or you will lock everyone out.", "error")
        return redirect(url_for("users"))
    if me and target["id"] == me["id"] and not active:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("users"))

    if email:
        other = db.get_user_by_email(email)
        if other and other["id"] != user_id:
            flash("That email address is already used by another account.", "error")
            return redirect(url_for("users"))

    db.update_user(user_id, full_name=full_name, role=role if role in ROLES else None, active=active)
    if email != (target["email"] or "").lower():
        db.set_user_email(user_id, email or None)
    flash("User updated.", "success")
    return redirect(url_for("users"))


def _other_active_admins(exclude_user_id):
    """How many active administrators there would still be without this one."""
    return sum(1 for u in db.list_users()
               if u["id"] != exclude_user_id and u["active"] and is_admin_role(u["role"]))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@auth.admin_required
def user_delete(user_id):
    me = auth.current_user()
    target = db.get_user(user_id)
    if target is None:
        flash("That user no longer exists.", "error")
        return redirect(url_for("users"))
    if me and target["id"] == me["id"]:
        flash("You cannot delete the account you are signed in with.", "error")
        return redirect(url_for("users"))
    if is_admin_role(target["role"]) and _other_active_admins(user_id) == 0:
        flash("This is the only administrator left. Give somebody else an "
              "administrator role before deleting this one.", "error")
        return redirect(url_for("users"))

    db.delete_user(user_id)
    flash("Account for {} deleted. Their sign-in history and the records they "
          "created are kept.".format(target["username"]), "success")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/reset-password", methods=["POST"])
@auth.admin_required
def user_reset_password(user_id):
    import secrets
    temp_password = secrets.token_urlsafe(9)
    db.set_password(user_id, auth.hash_password(temp_password), must_change_password=True)
    flash("Temporary password for this user: {}  (shown once - share it securely; they must change it at next login)".format(temp_password), "success")
    return redirect(url_for("users"))


@app.route("/settings", methods=["GET", "POST"])
@auth.admin_required
def settings():
    if request.method == "POST":
        data = {
            "smtp_host": request.form.get("smtp_host", "").strip(),
            "smtp_port": request.form.get("smtp_port", "587").strip(),
            "smtp_username": request.form.get("smtp_username", "").strip(),
            "smtp_password": request.form.get("smtp_password", ""),
            "smtp_use_tls": "1" if request.form.get("smtp_use_tls") == "on" else "0",
            "digest_from": request.form.get("digest_from", "").strip(),
            "digest_to": request.form.get("digest_to", "").strip(),
            "digest_horizon_days": request.form.get("digest_horizon_days", "90").strip(),
        }
        existing = db.get_settings()
        if not data["smtp_password"]:
            data["smtp_password"] = existing.get("smtp_password", "")
        note = request.form.get("leave_policy_note", "").strip()
        data["leave_policy_note"] = note
        data["leave_policy_updated"] = (date.today().isoformat() if note != existing.get("leave_policy_note", "")
                                         else existing.get("leave_policy_updated", ""))
        db.save_settings(data)
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", settings=db.get_settings(), holidays=db.list_holidays())


@app.route("/settings/holiday/add", methods=["POST"])
@auth.admin_required
def holiday_add():
    name = request.form.get("name", "").strip()
    holiday_date = request.form.get("holiday_date", "").strip()
    if name and holiday_date:
        db.add_holiday(name, holiday_date)
        flash("Holiday added.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/holiday/<int:holiday_id>/delete", methods=["POST"])
@auth.admin_required
def holiday_delete(holiday_id):
    db.delete_holiday(holiday_id)
    flash("Holiday removed.", "success")
    return redirect(url_for("settings"))


@app.route("/settings/send-test", methods=["POST"])
@auth.admin_required
def settings_send_test():
    import email_digest
    ok = email_digest.send_digest(force=True)
    flash("Test digest sent." if ok else "Could not send the test digest - check your SMTP settings.",
          "success" if ok else "error")
    return redirect(url_for("settings"))


@app.route("/login-activity")
@auth.admin_required
def login_activity():
    return render_template("login_activity.html", logins=db.list_login_log(150))


@app.errorhandler(413)
def too_large(e):
    """Flask rejects an over-sized upload before any view runs, so without
    this the person gets a bare browser error with no idea what happened."""
    return render_template("error.html", code=413,
                            message="That file is too large to upload. The limit for one "
                                    "request is 20 MB. Resize the picture, or attach a "
                                    "smaller file, and try again."), 413


@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                            message="You don't have access to this section. Ask an administrator to change your role if you need it."), 403


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("\n  DHARANI 360 is running.")
    print("  Open this address in your browser:  http://127.0.0.1:{}\n".format(port))
    app.run(host="127.0.0.1", port=port, debug=False)
