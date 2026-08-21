# -*- coding: utf-8 -*-
"""
DHARANI 360 - Database layer
=============================
Every form in forms_data.FORMS becomes one real SQLite table (the
"register"). This module creates those tables automatically on first
run, and provides generic insert/list/get/update/delete/search
functions driven purely by the form metadata - so adding a 77th form
to forms_data.py is enough; nothing here needs to change.
"""
import sqlite3
import hashlib
import json
import os
import csv
import io
import uuid
from datetime import datetime, date, timedelta

from forms_data import (FORMS, FORMS_BY_CODE, DEPARTMENTS, table_name,
                         FIELD_TO_FORMS, linkable_fields)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
DB_PATH = os.path.join(INSTANCE_DIR, "dharani360.db")
UPLOADS_DIR = os.path.join(INSTANCE_DIR, "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
PHOTOS_DIR = os.path.join(INSTANCE_DIR, "photos")
os.makedirs(PHOTOS_DIR, exist_ok=True)
CHAT_DIR = os.path.join(INSTANCE_DIR, "chatfiles")
os.makedirs(CHAT_DIR, exist_ok=True)
PHOTO_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_PHOTO_BYTES = 15 * 1024 * 1024  # 15MB - a phone photo is often 5-10MB

TYPE_TO_SQL = {
    "number": "REAL",
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS counters (
        form_code TEXT PRIMARY KEY,
        seq INTEGER NOT NULL DEFAULT 0
    )""")
    for form in FORMS:
        tname = table_name(form["code"])
        cols = ["id INTEGER PRIMARY KEY AUTOINCREMENT",
                "doc_no TEXT UNIQUE",
                "created_at TEXT",
                "updated_at TEXT",
                "created_by TEXT",
                "status TEXT",
                "notes TEXT"]
        for field in form["fields"]:
            sql_type = TYPE_TO_SQL.get(field["type"], "TEXT")
            cols.append('"{}" {}'.format(field["name"], sql_type))
        ddl = "CREATE TABLE IF NOT EXISTS {} ({})".format(tname, ", ".join(cols))
        cur.execute(ddl)
        cur.execute("INSERT OR IGNORE INTO counters (form_code, seq) VALUES (?, 0)", (form["code"],))
        # Migration: this table may already exist from before a field was
        # added to forms_data.py (e.g. on an install the user already ran).
        # CREATE TABLE IF NOT EXISTS won't add new columns, so do it here.
        existing_cols = {row["name"] for row in cur.execute('PRAGMA table_info({})'.format(tname)).fetchall()}
        for field in form["fields"]:
            if field["name"] not in existing_cols:
                sql_type = TYPE_TO_SQL.get(field["type"], "TEXT")
                cur.execute('ALTER TABLE {} ADD COLUMN "{}" {}'.format(tname, field["name"], sql_type))

    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        role TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        must_change_password INTEGER NOT NULL DEFAULT 1,
        created_at TEXT,
        last_login TEXT
    )""")
    user_cols = {row["name"] for row in cur.execute('PRAGMA table_info(users)').fetchall()}
    if "photo_path" not in user_cols:
        cur.execute('ALTER TABLE users ADD COLUMN photo_path TEXT')
    # Sign-in moved from username to work email (Supabase Auth is keyed on
    # email). The username column stays: it is the attribution key written
    # into created_by on every record, and rewriting history is not worth it.
    if "email" not in user_cols:
        cur.execute('ALTER TABLE users ADD COLUMN email TEXT')
    # Each person's own meeting room - a Google Meet, Zoom, Teams or Webex
    # link they paste once. DHARANI 360 rings, invites and logs; the video
    # itself happens in the provider the company is allowed to use.
    if "meeting_link" not in user_cols:
        cur.execute('ALTER TABLE users ADD COLUMN meeting_link TEXT')
    cur.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email '
                'ON users (email COLLATE NOCASE) WHERE email IS NOT NULL')

    cur.execute("""CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        form_code TEXT NOT NULL,
        record_id INTEGER NOT NULL,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        size_bytes INTEGER,
        uploaded_by TEXT,
        uploaded_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS todos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        color TEXT,
        done INTEGER NOT NULL DEFAULT 0,
        created_at TEXT
    )""")
    # A to-do used to be a binary done/not-done flag. The board view needs a
    # middle lane, so `status` was added alongside it. `done` is kept in sync
    # rather than dropped: the dashboard widget and the toggle button still
    # read it, and an older copy of this file must keep working against a
    # database this one has already migrated.
    todo_cols = {row["name"] for row in cur.execute('PRAGMA table_info(todos)').fetchall()}
    if "status" not in todo_cols:
        cur.execute('ALTER TABLE todos ADD COLUMN status TEXT')
        cur.execute("UPDATE todos SET status = CASE WHEN done = 1 THEN 'Done' ELSE 'To Do' END")
    cur.execute("UPDATE todos SET status = CASE WHEN done = 1 THEN 'Done' ELSE 'To Do' END "
                "WHERE status IS NULL OR status = ''")

    cur.execute("""CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT,
        meeting_date TEXT,
        start_time TEXT,
        end_time TEXT,
        link TEXT,
        attendees TEXT,
        created_by TEXT,
        created_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS library_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        folder TEXT,
        description TEXT,
        size_bytes INTEGER,
        uploaded_by TEXT,
        uploaded_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT,
        read_at TEXT
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_pair ON chat_messages (from_user, to_user, id)")

    # A message is no longer only text. "kind" says what it carries and "meta"
    # holds the JSON payload for the richer kinds, so one table still drives
    # the whole conversation:
    #   text   - what somebody typed
    #   file   - an attachment; attach_* columns are filled
    #   share  - a record, register or call handed to a colleague
    #   call   - a call was started, joined, missed or ended
    chat_cols = {row["name"] for row in cur.execute("PRAGMA table_info(chat_messages)").fetchall()}
    for col, decl in (("kind", "TEXT"), ("meta", "TEXT"), ("attach_name", "TEXT"),
                      ("attach_stored", "TEXT"), ("attach_size", "INTEGER"),
                      ("delivered_at", "TEXT")):
        if col not in chat_cols:
            cur.execute("ALTER TABLE chat_messages ADD COLUMN {} {}".format(col, decl))
    cur.execute("UPDATE chat_messages SET kind = 'text' WHERE kind IS NULL")

    # A call is a live thing with a start and an end. It is kept apart from the
    # SAL-009 Call Log register on purpose: this table is the running session,
    # the register is the permanent record written when the call finishes.
    cur.execute("""CREATE TABLE IF NOT EXISTS call_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT NOT NULL,
        mode TEXT,
        started_by TEXT NOT NULL,
        other_user TEXT,
        contact_name TEXT,
        contact_number TEXT,
        guest_token TEXT,
        subject TEXT,
        started_at TEXT,
        answered_at TEXT,
        ended_at TEXT,
        duration_seconds INTEGER,
        outcome TEXT,
        record_id INTEGER,
        status TEXT
    )""")
    call_cols = {row["name"] for row in cur.execute("PRAGMA table_info(call_sessions)").fetchall()}
    if "meeting_url" not in call_cols:
        cur.execute("ALTER TABLE call_sessions ADD COLUMN meeting_url TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_call_live ON call_sessions (status, other_user, id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_call_guest ON call_sessions (guest_token)")

    cur.execute("""CREATE TABLE IF NOT EXISTS holidays (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        holiday_date TEXT NOT NULL,
        created_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        text TEXT NOT NULL,
        color TEXT,
        created_at TEXT
    )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS login_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        full_name TEXT,
        role TEXT,
        ip_address TEXT,
        at TEXT
    )""")

    conn.commit()

    # Seed a default administrator on first run only.
    row = cur.execute("SELECT COUNT(*) FROM users").fetchone()
    if row[0] == 0:
        from werkzeug.security import generate_password_hash
        cur.execute(
            "INSERT INTO users (username, password_hash, full_name, role, active, must_change_password, created_at) "
            "VALUES (?, ?, ?, ?, 1, 1, ?)",
            ("admin", generate_password_hash("dharani360"), "Administrator", "Director",
             datetime.utcnow().isoformat(timespec="seconds"))
        )
        conn.commit()

    conn.close()


def next_doc_no(form_code):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE counters SET seq = seq + 1 WHERE form_code = ?", (form_code,))
    cur.execute("SELECT seq FROM counters WHERE form_code = ?", (form_code,))
    seq = cur.fetchone()[0]
    conn.commit()
    conn.close()
    return "DR-{}-{:04d}".format(form_code, seq)


def insert_record(form_code, data, created_by="Admin"):
    form = FORMS_BY_CODE[form_code]
    tname = table_name(form_code)
    doc_no = next_doc_no(form_code)
    now = datetime.utcnow().isoformat(timespec="seconds")
    field_names = [f["name"] for f in form["fields"]]
    columns = ["doc_no", "created_at", "updated_at", "created_by", "status", "notes"] + field_names
    values = [doc_no, now, now, created_by, data.get("status") or (form["status_options"][0] if form.get("status_options") else ""),
              data.get("notes", "")]
    for name in field_names:
        values.append(data.get(name, ""))
    placeholders = ", ".join(["?"] * len(columns))
    col_sql = ", ".join('"{}"'.format(c) for c in columns)
    conn = get_conn()
    conn.execute("INSERT INTO {} ({}) VALUES ({})".format(tname, col_sql, placeholders), values)
    conn.commit()
    conn.close()
    return doc_no


def record_id_for_doc(form_code, doc_no):
    """Row id for a document number. insert_record() returns the doc_no, which
    is what people read; this is what url_for() needs."""
    if not doc_no:
        return None
    conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM {} WHERE doc_no = ?".format(table_name(form_code)),
                           (doc_no,)).fetchone()
    except sqlite3.Error:
        row = None
    conn.close()
    return row["id"] if row else None


def update_record(form_code, record_id, data):
    form = FORMS_BY_CODE[form_code]
    tname = table_name(form_code)
    field_names = [f["name"] for f in form["fields"]]
    now = datetime.utcnow().isoformat(timespec="seconds")
    set_cols = ["updated_at = ?", "status = ?", "notes = ?"]
    values = [now, data.get("status", ""), data.get("notes", "")]
    for name in field_names:
        set_cols.append('"{}" = ?'.format(name))
        values.append(data.get(name, ""))
    values.append(record_id)
    conn = get_conn()
    conn.execute("UPDATE {} SET {} WHERE id = ?".format(tname, ", ".join(set_cols)), values)
    conn.commit()
    conn.close()


def delete_record(form_code, record_id):
    tname = table_name(form_code)
    conn = get_conn()
    conn.execute("DELETE FROM {} WHERE id = ?".format(tname), (record_id,))
    conn.commit()
    conn.close()
    for att in get_attachments(form_code, record_id):
        _delete_attachment_file(att)
    conn = get_conn()
    conn.execute("DELETE FROM attachments WHERE form_code = ? AND record_id = ?", (form_code, record_id))
    conn.commit()
    conn.close()


SORTABLE_BASE_COLUMNS = {"id", "doc_no", "created_at", "updated_at", "created_by", "status"}


def get_records(form_code, q=None, sort=None, direction="desc", page=None, page_size=25):
    """Returns (rows, total_count). If page is None, all matching rows are
    returned (used by CSV export and internal lookups)."""
    form = FORMS_BY_CODE[form_code]
    tname = table_name(form_code)
    valid_columns = SORTABLE_BASE_COLUMNS | {f["name"] for f in form["fields"]}
    sort_col = sort if sort in valid_columns else "id"
    sort_dir = "ASC" if str(direction).lower() == "asc" else "DESC"

    conn = get_conn()
    params = []
    where_sql = ""
    if q:
        text_fields = [f["name"] for f in form["fields"] if f["type"] in ("text", "textarea", "email", "tel", "select")]
        text_fields += ["doc_no", "created_by", "status", "notes"]
        where_sql = " WHERE " + " OR ".join('"{}" LIKE ?'.format(c) for c in text_fields)
        params = ["%{}%".format(q)] * len(text_fields)

    total = conn.execute("SELECT COUNT(*) FROM {}{}".format(tname, where_sql), params).fetchone()[0]

    order_sql = ' ORDER BY "{}" {}'.format(sort_col, sort_dir)
    if sort_col != "id":
        order_sql += ", id DESC"
    limit_sql = ""
    if page is not None:
        page = max(1, page)
        limit_sql = " LIMIT {} OFFSET {}".format(page_size, (page - 1) * page_size)

    rows = conn.execute("SELECT * FROM {}{}{}{}".format(tname, where_sql, order_sql, limit_sql), params).fetchall()
    conn.close()
    return [dict(r) for r in rows], total


def get_id_by_doc_no(form_code, doc_no):
    tname = table_name(form_code)
    conn = get_conn()
    row = conn.execute("SELECT id FROM {} WHERE doc_no = ?".format(tname), (doc_no,)).fetchone()
    conn.close()
    return row["id"] if row else None


def get_record(form_code, record_id):
    tname = table_name(form_code)
    conn = get_conn()
    row = conn.execute("SELECT * FROM {} WHERE id = ?".format(tname), (record_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def count_records(form_code):
    tname = table_name(form_code)
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM {}".format(tname)).fetchone()[0]
    conn.close()
    return n


def all_counts():
    conn = get_conn()
    result = {}
    for form in FORMS:
        tname = table_name(form["code"])
        n = conn.execute("SELECT COUNT(*) FROM {}".format(tname)).fetchone()[0]
        result[form["code"]] = n
    conn.close()
    return result


def _parse_date(value):
    if not value:
        return None
    value = str(value)[:10]
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def rag_status(days_left):
    """Given days until expiry (can be negative), return RED/AMBER/GREEN."""
    if days_left is None:
        return None
    if days_left <= 30:
        return "RED"
    if days_left <= 90:
        return "AMBER"
    return "GREEN"


def status_color(status):
    if not status:
        return "GREY"
    s = status.strip().lower()
    green = {"approved", "completed", "closed", "verified", "resolved", "valid", "active", "paid",
             "complete", "compliant", "fulfilled", "converted", "signed", "current"}
    red = {"rejected", "expired", "disputed", "escalated", "overdue", "lost", "terminated",
           "cancelled", "withdrawn", "high risk", "high"}
    amber = {"pending", "open", "in progress", "under investigation", "investigating", "new",
             "contacted", "draft", "requested", "incomplete", "awaiting response", "expiring soon",
             "medium risk", "medium", "needs review", "scheduled", "qualified"}
    if s in green:
        return "GREEN"
    if s in red:
        return "RED"
    if s in amber:
        return "AMBER"
    return "BLUE"


def expiring_items(horizon_days=90):
    """Scan every form that has an expiry_field and return items due within
    horizon_days (including already-overdue), sorted soonest first."""
    today = date.today()
    items = []
    conn = get_conn()
    for form in FORMS:
        expiry_field = form.get("expiry_field")
        if not expiry_field:
            continue
        tname = table_name(form["code"])
        rows = conn.execute('SELECT id, doc_no, status, "{}" as expiry FROM {}'.format(expiry_field, tname)).fetchall()
        for r in rows:
            d = _parse_date(r["expiry"])
            if not d:
                continue
            days_left = (d - today).days
            if days_left <= horizon_days:
                items.append({
                    "dept": form["dept"],
                    "form_code": form["code"],
                    "form_title": form["title"],
                    "record_id": r["id"],
                    "doc_no": r["doc_no"],
                    "expiry_date": r["expiry"],
                    "days_left": days_left,
                    "rag": rag_status(days_left),
                })
    conn.close()
    items.sort(key=lambda x: x["days_left"])
    return items


def recent_activity(limit=15):
    conn = get_conn()
    items = []
    for form in FORMS:
        tname = table_name(form["code"])
        rows = conn.execute(
            "SELECT id, doc_no, created_at, created_by, status FROM {} ORDER BY id DESC LIMIT 5".format(tname)
        ).fetchall()
        for r in rows:
            items.append({
                "dept": form["dept"],
                "form_code": form["code"],
                "form_title": form["title"],
                "record_id": r["id"],
                "doc_no": r["doc_no"],
                "created_at": r["created_at"],
                "created_by": r["created_by"],
                "status": r["status"],
            })
    conn.close()
    items.sort(key=lambda x: x["created_at"] or "", reverse=True)
    return items[:limit]


def global_search(q):
    if not q:
        return []
    conn = get_conn()
    results = []
    like = "%{}%".format(q)
    for form in FORMS:
        tname = table_name(form["code"])
        text_fields = [f["name"] for f in form["fields"] if f["type"] in ("text", "textarea", "email", "tel", "select")]
        text_fields += ["doc_no", "created_by", "status", "notes"]
        where = " OR ".join('"{}" LIKE ?'.format(c) for c in text_fields)
        params = [like] * len(text_fields)
        try:
            rows = conn.execute("SELECT * FROM {} WHERE {} ORDER BY id DESC LIMIT 25".format(tname, where), params).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for r in rows:
            results.append({
                "dept": form["dept"],
                "form_code": form["code"],
                "form_title": form["title"],
                "record": dict(r),
            })
    conn.close()
    return results


def export_csv(form_code):
    form = FORMS_BY_CODE[form_code]
    rows, _total = get_records(form_code, page=None)
    output = io.StringIO()
    field_names = [f["name"] for f in form["fields"]]
    header = ["doc_no", "status", "created_at", "created_by"] + field_names + ["notes"]
    writer = csv.writer(output)
    writer.writerow(header)
    for row in rows:
        writer.writerow([row.get(h, "") for h in header])
    return output.getvalue()


def field_counts(form_code, field, limit=None):
    """Group-by count of a field's distinct values (blank values excluded)."""
    tname = table_name(form_code)
    conn = get_conn()
    rows = conn.execute(
        'SELECT "{0}" as v, COUNT(*) as n FROM {1} WHERE "{0}" IS NOT NULL AND TRIM("{0}") != "" '
        'GROUP BY "{0}" ORDER BY n DESC'.format(field, tname)
    ).fetchall()
    conn.close()
    result = [{"value": r["v"], "count": r["n"]} for r in rows]
    if limit:
        result = result[:limit]
    return result


def count_where_in(form_code, field, values):
    """Count of records whose field value is (case-insensitively) one of values."""
    if not values:
        return 0
    tname = table_name(form_code)
    conn = get_conn()
    placeholders = ",".join("?" * len(values))
    n = conn.execute(
        'SELECT COUNT(*) FROM {} WHERE "{}" COLLATE NOCASE IN ({})'.format(tname, field, placeholders),
        values
    ).fetchone()[0]
    conn.close()
    return n


def count_where(form_code, conditions):
    """Count of records matching multiple AND-ed conditions.

    conditions: list of (field, op, value) tuples, op in:
      'in'  - value is a list, case-insensitive membership
      'eq'  - value is a scalar, exact match (e.g. a date string)
      'gte' - value is a scalar, field >= value (e.g. a date string)
    Used by dashboards that need combined filters (e.g. attendance
    "Present" AND date == today) that count_where_in alone can't express.
    """
    tname = table_name(form_code)
    conn = get_conn()
    clauses, params = [], []
    for field, op, value in conditions:
        if op == "in":
            if not value:
                conn.close()
                return 0
            placeholders = ",".join("?" * len(value))
            clauses.append('"{}" COLLATE NOCASE IN ({})'.format(field, placeholders))
            params.extend(value)
        elif op == "eq":
            clauses.append('"{}" = ?'.format(field))
            params.append(value)
        elif op == "gte":
            clauses.append('"{}" >= ?'.format(field))
            params.append(value)
        elif op == "lt":
            clauses.append('"{}" < ? AND "{}" IS NOT NULL AND TRIM("{}") != ""'.format(field, field, field))
            params.append(value)
        elif op == "not_in":
            if value:
                placeholders = ",".join("?" * len(value))
                clauses.append('("{}" IS NULL OR "{}" COLLATE NOCASE NOT IN ({}))'.format(field, field, placeholders))
                params.extend(value)
    where_sql = " WHERE " + " AND ".join(clauses) if clauses else ""
    n = conn.execute("SELECT COUNT(*) FROM {}{}".format(tname, where_sql), params).fetchone()[0]
    conn.close()
    return n


def records_where_in(form_code, field, values, limit=10, order_by="id DESC"):
    """Rows whose field value is (case-insensitively) one of values, most recent first."""
    if not values:
        return []
    tname = table_name(form_code)
    conn = get_conn()
    placeholders = ",".join("?" * len(values))
    rows = conn.execute(
        'SELECT * FROM {} WHERE "{}" COLLATE NOCASE IN ({}) ORDER BY {} LIMIT {}'.format(
            tname, field, placeholders, order_by, limit),
        values
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def sum_field(form_code, field, where_field=None, where_values=None):
    """Sum a numeric field, optionally filtered to rows where where_field is in where_values."""
    tname = table_name(form_code)
    conn = get_conn()
    if where_field and where_values:
        placeholders = ",".join("?" * len(where_values))
        val = conn.execute(
            'SELECT COALESCE(SUM("{}"),0) FROM {} WHERE "{}" COLLATE NOCASE IN ({})'.format(
                field, tname, where_field, placeholders),
            where_values
        ).fetchone()[0]
    else:
        val = conn.execute('SELECT COALESCE(SUM("{}"),0) FROM {}'.format(field, tname)).fetchone()[0]
    conn.close()
    return val or 0


def latest_value(form_code, field, order_by="id DESC"):
    """Most recent non-null value of a field (e.g. running petty-cash balance)."""
    tname = table_name(form_code)
    conn = get_conn()
    row = conn.execute(
        'SELECT "{}" as v FROM {} WHERE "{}" IS NOT NULL AND TRIM("{}") != "" ORDER BY {} LIMIT 1'.format(
            field, tname, field, field, order_by)
    ).fetchone()
    conn.close()
    return row["v"] if row else None


def records_upcoming(form_code, date_field, days_ahead=14, include_overdue=True, limit=10):
    """Records whose date_field falls within [today .. today+days_ahead] (optionally
    including already-overdue dates), soonest first."""
    tname = table_name(form_code)
    conn = get_conn()
    rows = conn.execute(
        'SELECT * FROM {} WHERE "{}" IS NOT NULL AND TRIM("{}") != ""'.format(tname, date_field, date_field)
    ).fetchall()
    conn.close()
    today = date.today()
    out = []
    for r in rows:
        d = _parse_date(r[date_field])
        if not d:
            continue
        days = (d - today).days
        if days <= days_ahead and (include_overdue or days >= 0):
            rd = dict(r)
            rd["_days"] = days
            out.append(rd)
    out.sort(key=lambda x: x["_days"])
    return out[:limit]


def dept_summary():
    """Per-department counts and urgency rollup for the dashboard."""
    counts = all_counts()
    exp_items = expiring_items(horizon_days=90)
    summary = {}
    for d in DEPARTMENTS:
        dept_forms = [f for f in FORMS if f["dept"] == d["code"]]
        total = sum(counts.get(f["code"], 0) for f in dept_forms)
        red = sum(1 for i in exp_items if i["dept"] == d["code"] and i["rag"] == "RED")
        amber = sum(1 for i in exp_items if i["dept"] == d["code"] and i["rag"] == "AMBER")
        summary[d["code"]] = {"total": total, "red": red, "amber": amber, "forms": len(dept_forms)}
    return summary


# ============================================================================
# Related records (cross-register linking)
# ============================================================================

def related_records(form_code, record_id, limit_per_field=15):
    """For every linkable field on this record that has a value, find every
    OTHER record (in any register) that shares the same value in a
    same-named field. Returns a list of {field, value, matches: [...]}."""
    form = FORMS_BY_CODE[form_code]
    record = get_record(form_code, record_id)
    if not record:
        return []
    conn = get_conn()
    results = []
    for field_name in linkable_fields(form_code):
        value = (record.get(field_name) or "").strip()
        if not value:
            continue
        matches = []
        for other_code in FIELD_TO_FORMS.get(field_name, []):
            other_tname = table_name(other_code)
            other_form = FORMS_BY_CODE[other_code]
            rows = conn.execute(
                'SELECT id, doc_no, status FROM {} WHERE "{}" = ? COLLATE NOCASE'.format(other_tname, field_name),
                (value,)
            ).fetchall()
            for r in rows:
                if other_code == form_code and r["id"] == record_id:
                    continue
                matches.append({
                    "form_code": other_code,
                    "form_title": other_form["title"],
                    "dept": other_form["dept"],
                    "record_id": r["id"],
                    "doc_no": r["doc_no"],
                    "status": r["status"],
                })
        if matches:
            results.append({"field": field_name, "value": value, "matches": matches[:limit_per_field]})
    conn.close()
    return results


# ============================================================================
# Users
# ============================================================================

def get_user(user_id):
    if not user_id:
        return None
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_username(username):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                       ((email or "").strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_user_email(user_id, email):
    conn = get_conn()
    conn.execute("UPDATE users SET email = ? WHERE id = ?", ((email or "").strip().lower(), user_id))
    conn.commit()
    conn.close()


def set_user_active(user_id, active):
    conn = get_conn()
    conn.execute("UPDATE users SET active = ? WHERE id = ?", (1 if active else 0, user_id))
    conn.commit()
    conn.close()


def list_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY username").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(username, password_hash, full_name, role, must_change_password=True):
    """Create a login account and return its new id.

    The id is returned so the caller can immediately attach the work email,
    which is what sign-in actually uses.
    """
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role, active, must_change_password, created_at) "
        "VALUES (?, ?, ?, ?, 1, ?, ?)",
        (username, password_hash, full_name, role, 1 if must_change_password else 0,
         datetime.utcnow().isoformat(timespec="seconds"))
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_user(user_id, full_name=None, role=None, active=None, meeting_link=None):
    sets, values = [], []
    if full_name is not None:
        sets.append("full_name = ?"); values.append(full_name)
    if meeting_link is not None:
        sets.append("meeting_link = ?"); values.append(meeting_link or None)
    if role is not None:
        sets.append("role = ?"); values.append(role)
    if active is not None:
        sets.append("active = ?"); values.append(1 if active else 0)
    if not sets:
        return
    values.append(user_id)
    conn = get_conn()
    conn.execute("UPDATE users SET {} WHERE id = ?".format(", ".join(sets)), values)
    conn.commit()
    conn.close()


def delete_user(user_id):
    """Remove a login account.

    Deliberately narrow: the account itself and the personal scratch data
    that belongs to nobody else (their to-dos and notes) are removed.
    Everything that forms the audit trail is kept - sign-in history, chat
    messages, and every register record they created, which stores the
    creator's name as text and so is unaffected. A compliance system must
    not lose who did what because somebody left.
    """
    conn = get_conn()
    try:
        conn.execute("DELETE FROM todos WHERE user_id = ?", (user_id,))
    except sqlite3.Error:
        pass
    try:
        conn.execute("DELETE FROM notes WHERE user_id = ?", (user_id,))
    except sqlite3.Error:
        pass
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def set_password(user_id, password_hash, must_change_password=False):
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash = ?, must_change_password = ? WHERE id = ?",
                 (password_hash, 1 if must_change_password else 0, user_id))
    conn.commit()
    conn.close()


def record_login(user_id, ip_address=None):
    conn = get_conn()
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user_id))
    user = conn.execute("SELECT username, full_name, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if user:
        conn.execute(
            "INSERT INTO login_log (user_id, username, full_name, role, ip_address, at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, user["username"], user["full_name"], user["role"], ip_address, now)
        )
    conn.commit()
    conn.close()


def list_login_log(limit=100):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM login_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================================
# Attachments
# ============================================================================

ALLOWED_ATTACHMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "doc", "docx",
                                  "xls", "xlsx", "txt", "csv"}
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024  # 15MB


def _attachment_dir(form_code, record_id):
    d = os.path.join(UPLOADS_DIR, form_code, str(record_id))
    os.makedirs(d, exist_ok=True)
    return d


def add_attachment(form_code, record_id, original_name, file_bytes, uploaded_by="Admin"):
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    stored_name = "{}.{}".format(uuid.uuid4().hex, ext) if ext else uuid.uuid4().hex
    path = os.path.join(_attachment_dir(form_code, record_id), stored_name)
    with open(path, "wb") as fh:
        fh.write(file_bytes)
    conn = get_conn()
    conn.execute(
        "INSERT INTO attachments (form_code, record_id, original_name, stored_name, size_bytes, uploaded_by, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (form_code, record_id, original_name, stored_name, len(file_bytes), uploaded_by,
         datetime.utcnow().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def get_attachments(form_code, record_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM attachments WHERE form_code = ? AND record_id = ? ORDER BY id DESC",
        (form_code, record_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_attachment(attachment_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def attachment_counts_for(form_code, record_ids):
    if not record_ids:
        return {}
    conn = get_conn()
    placeholders = ",".join("?" * len(record_ids))
    rows = conn.execute(
        "SELECT record_id, COUNT(*) as n FROM attachments WHERE form_code = ? AND record_id IN ({}) GROUP BY record_id".format(placeholders),
        [form_code] + list(record_ids)
    ).fetchall()
    conn.close()
    return {r["record_id"]: r["n"] for r in rows}


def _delete_attachment_file(att):
    path = os.path.join(_attachment_dir(att["form_code"], att["record_id"]), att["stored_name"])
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def delete_attachment(attachment_id):
    att = get_attachment(attachment_id)
    if not att:
        return
    _delete_attachment_file(att)
    conn = get_conn()
    conn.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
    conn.commit()
    conn.close()


def attachment_file_path(att):
    return os.path.join(_attachment_dir(att["form_code"], att["record_id"]), att["stored_name"])


def list_all_attachments(depts_allowed=None, limit=300):
    """Every file attached to any record, newest first - the data behind the
    File Manager. Filtered to the departments the current user can see."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM attachments ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    items = []
    for r in rows:
        form = FORMS_BY_CODE.get(r["form_code"])
        if not form:
            continue
        if depts_allowed is not None and form["dept"] not in depts_allowed:
            continue
        d = dict(r)
        d["form_title"] = form["title"]
        d["dept"] = form["dept"]
        items.append(d)
    return items


# ============================================================================
# Settings (SMTP / compliance-digest configuration)
# ============================================================================

SETTINGS_KEYS = ["smtp_host", "smtp_port", "smtp_username", "smtp_password",
                  "smtp_use_tls", "digest_from", "digest_to", "digest_horizon_days",
                  "leave_policy_note", "leave_policy_updated"]


def get_settings():
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    values = {r["key"]: r["value"] for r in rows}
    return {k: values.get(k, "") for k in SETTINGS_KEYS}


def save_settings(data):
    conn = get_conn()
    for key in SETTINGS_KEYS:
        if key in data:
            conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(data[key])))
    conn.commit()
    conn.close()


# ============================================================================
# Photos (user avatars + employee record photos)
# ============================================================================

def save_uploaded_photo(subdir, key, file_storage):
    """Backwards-compatible wrapper: the path, or None."""
    relpath, _error = save_photo_checked(subdir, key, file_storage)
    return relpath


def save_photo_checked(subdir, key, file_storage):
    """Save an uploaded image and return (relative_path, error_message).

    Exactly one of the two is set. The earlier version returned None for
    every kind of failure, so a photo that was simply too large, or a HEIC
    straight off an iPhone, looked identical to no file at all - the upload
    just quietly did nothing. Each reason now comes back in words.

    If Pillow is installed the image is also downscaled to a sensible
    avatar size, which removes the size problem rather than reporting it.
    """
    if not file_storage or not file_storage.filename:
        return None, "No file was chosen."

    name = file_storage.filename
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext in ("heic", "heif"):
        return None, ("{} is an Apple HEIC photo, which browsers cannot display. "
                      "On the iPhone: Settings > Camera > Formats > Most Compatible, "
                      "then retake it - or save the picture as JPG first.".format(name))
    if ext not in PHOTO_EXTENSIONS:
        return None, ("{} is not an image this system accepts. Use {}."
                      .format(name, ", ".join(sorted(PHOTO_EXTENSIONS))))

    file_bytes = file_storage.read()
    if not file_bytes:
        return None, "That file is empty."

    file_bytes, ext = _shrink_image(file_bytes, ext)

    if len(file_bytes) > MAX_PHOTO_BYTES:
        return None, ("That picture is {:.1f} MB and the limit is {:.0f} MB. "
                      "Resize it, or install Pillow (run start.bat once with the "
                      "internet on) and the system will shrink it for you."
                      .format(len(file_bytes) / 1048576.0, MAX_PHOTO_BYTES / 1048576.0))

    d = os.path.join(PHOTOS_DIR, subdir, str(key))
    os.makedirs(d, exist_ok=True)
    # Clear any previous photo(s) for this key so old files don't pile up.
    for old in os.listdir(d):
        try:
            os.remove(os.path.join(d, old))
        except OSError:
            pass
    stored_name = "{}.{}".format(uuid.uuid4().hex, ext)
    try:
        with open(os.path.join(d, stored_name), "wb") as fh:
            fh.write(file_bytes)
    except OSError as exc:
        return None, "The picture could not be written to disk: {}".format(exc)
    return "{}/{}/{}".format(subdir, key, stored_name), None


PHOTO_MAX_EDGE = 900          # plenty for an avatar or a record photo


def _shrink_image(data, ext):
    """Downscale a large photo if Pillow is available.

    Pillow is optional on purpose - the app has always run on Flask alone,
    and it must keep doing so on a machine with no internet. Without it the
    bytes are returned untouched and the size check still applies.
    """
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, ext
    try:
        import io as _io
        img = Image.open(_io.BytesIO(data))
        img = ImageOps.exif_transpose(img)          # honour the phone's rotation
        if max(img.size) <= PHOTO_MAX_EDGE and len(data) <= MAX_PHOTO_BYTES:
            return data, ext
        img.thumbnail((PHOTO_MAX_EDGE, PHOTO_MAX_EDGE), Image.LANCZOS)
        out = _io.BytesIO()
        if img.mode in ("RGBA", "LA", "P") and ext in ("png", "webp", "gif"):
            img.convert("RGBA").save(out, format="PNG", optimize=True)
            return out.getvalue(), "png"
        img.convert("RGB").save(out, format="JPEG", quality=86, optimize=True)
        return out.getvalue(), "jpg"
    except Exception:
        # A file Pillow cannot read is not necessarily a broken upload -
        # fall back to storing it as it came in.
        return data, ext


def photo_disk_path(relative_path):
    if not relative_path:
        return None
    return os.path.join(PHOTOS_DIR, relative_path)


def update_user_photo(user_id, relative_path):
    conn = get_conn()
    conn.execute("UPDATE users SET photo_path = ? WHERE id = ?", (relative_path, user_id))
    conn.commit()
    conn.close()


def set_field(form_code, record_id, field_name, value):
    """Directly set one column on a record, bypassing the full form-fields
    update flow. Used for out-of-band updates like a photo upload."""
    tname = table_name(form_code)
    conn = get_conn()
    conn.execute('UPDATE {} SET "{}" = ?, updated_at = ? WHERE id = ?'.format(tname, field_name),
                 (value, datetime.utcnow().isoformat(timespec="seconds"), record_id))
    conn.commit()
    conn.close()


# ============================================================================
# Time-series / date-range helpers (dashboards)
# ============================================================================

def sum_field_by_month(form_code, amount_field, date_field, months=12, where_field=None, where_values=None):
    """Sum of amount_field grouped by calendar month (YYYY-MM) for the last
    `months` months, oldest first. Always returns one entry per month
    (0 if no records), suitable for a bar/line chart."""
    conn = get_conn()
    tname = table_name(form_code)
    clauses, params = ['"{}" IS NOT NULL'.format(date_field)], []
    if where_field and where_values:
        placeholders = ",".join("?" * len(where_values))
        clauses.append('"{}" COLLATE NOCASE IN ({})'.format(where_field, placeholders))
        params.extend(where_values)
    where_sql = " WHERE " + " AND ".join(clauses)
    rows = conn.execute(
        'SELECT substr("{0}",1,7) as ym, SUM("{1}") as total FROM {2}{3} GROUP BY ym'.format(
            date_field, amount_field, tname, where_sql), params
    ).fetchall()
    conn.close()
    by_month = {r["ym"]: (r["total"] or 0) for r in rows}
    out = []
    y, m = date.today().year, date.today().month
    keys = []
    for i in range(months - 1, -1, -1):
        yy, mm = y, m - i
        while mm <= 0:
            mm += 12
            yy -= 1
        keys.append("{:04d}-{:02d}".format(yy, mm))
    for ym in keys:
        label = datetime.strptime(ym, "%Y-%m").strftime("%b")
        out.append({"month": ym, "label": label, "total": by_month.get(ym, 0)})
    return out


def sum_field_since(form_code, field, date_field, since_iso, where_field=None, where_values=None):
    """Sum of a numeric field where date_field >= since_iso, optionally
    filtered to where_field in where_values."""
    tname = table_name(form_code)
    conn = get_conn()
    clauses, params = ['"{}" >= ?'.format(date_field)], [since_iso]
    if where_field and where_values:
        placeholders = ",".join("?" * len(where_values))
        clauses.append('"{}" COLLATE NOCASE IN ({})'.format(where_field, placeholders))
        params.extend(where_values)
    where_sql = " WHERE " + " AND ".join(clauses)
    val = conn.execute('SELECT COALESCE(SUM("{}"),0) FROM {}{}'.format(field, tname, where_sql), params).fetchone()[0]
    conn.close()
    return val or 0


def upcoming_birthdays(form_code, dob_field, name_field, days_ahead=30, extra_where=None):
    """Employees whose birthday (month/day, year-independent) falls within
    the next days_ahead days, including today. extra_where: optional
    (field, values) to further filter (e.g. department)."""
    tname = table_name(form_code)
    conn = get_conn()
    sql = 'SELECT * FROM {} WHERE "{}" IS NOT NULL AND TRIM("{}") != ""'.format(tname, dob_field, dob_field)
    params = []
    if extra_where:
        field, values = extra_where
        if not values:
            conn.close()
            return []
        placeholders = ",".join("?" * len(values))
        sql += ' AND "{}" COLLATE NOCASE IN ({})'.format(field, placeholders)
        params.extend(values)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    today = date.today()
    out = []
    for r in rows:
        d = _parse_date(r[dob_field])
        if not d:
            continue
        this_year = d.replace(year=today.year)
        if this_year < today:
            this_year = this_year.replace(year=today.year + 1)
        days = (this_year - today).days
        if 0 <= days <= days_ahead:
            rd = dict(r)
            rd["_days"] = days
            rd["_name"] = rd.get(name_field)
            out.append(rd)
    out.sort(key=lambda x: x["_days"])
    return out


# ============================================================================
# Todos (personal, per-user)
# ============================================================================

TODO_STATUSES = ["To Do", "In Progress", "Done"]


def list_todos(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM todos WHERE user_id = ? ORDER BY done ASC, id DESC", (user_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        # Belt and braces: a row written by an older build has no status.
        if not d.get("status"):
            d["status"] = "Done" if d.get("done") else "To Do"
        out.append(d)
    return out


def todo_board(user_id):
    """The same to-dos, grouped into the three board lanes in lane order."""
    board = {s: [] for s in TODO_STATUSES}
    for t in list_todos(user_id):
        board.setdefault(t["status"], []).append(t)
    return board


def add_todo(user_id, text, color="blue", status="To Do"):
    if status not in TODO_STATUSES:
        status = "To Do"
    conn = get_conn()
    conn.execute("INSERT INTO todos (user_id, text, color, done, status, created_at) "
                 "VALUES (?, ?, ?, ?, ?, ?)",
                 (user_id, text, color, 1 if status == "Done" else 0, status,
                  datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def toggle_todo(todo_id, user_id):
    """Tick / untick. Ticking always lands in Done; unticking returns the card
    to To Do, which is the only lane an untick can unambiguously mean."""
    conn = get_conn()
    conn.execute("UPDATE todos SET done = 1 - done, "
                 "status = CASE WHEN done = 1 THEN 'To Do' ELSE 'Done' END "
                 "WHERE id = ? AND user_id = ?", (todo_id, user_id))
    conn.commit()
    conn.close()


def set_todo_status(todo_id, user_id, status):
    """Move a card between board lanes, keeping the legacy `done` flag true to
    the lane so nothing that still reads `done` goes stale."""
    if status not in TODO_STATUSES:
        return
    conn = get_conn()
    conn.execute("UPDATE todos SET status = ?, done = ? WHERE id = ? AND user_id = ?",
                 (status, 1 if status == "Done" else 0, todo_id, user_id))
    conn.commit()
    conn.close()


def delete_todo(todo_id, user_id):
    conn = get_conn()
    conn.execute("DELETE FROM todos WHERE id = ? AND user_id = ?", (todo_id, user_id))
    conn.commit()
    conn.close()


# ============================================================================
# Personal sticky notes
# ============================================================================

def list_notes(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_note(user_id, text, color="blue"):
    conn = get_conn()
    conn.execute("INSERT INTO notes (user_id, text, color, created_at) VALUES (?, ?, ?, ?)",
                 (user_id, text, color, datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def delete_note(note_id, user_id):
    conn = get_conn()
    conn.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    conn.close()


# ============================================================================
# Meetings
# ============================================================================

def list_meetings_upcoming(limit=10, since_iso=None):
    since_iso = since_iso or date.today().isoformat()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM meetings WHERE meeting_date >= ? ORDER BY meeting_date ASC, start_time ASC LIMIT ?",
        (since_iso, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_meetings_between(start_iso, end_iso):
    """All meetings/events whose date falls inside [start_iso, end_iso]."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM meetings WHERE meeting_date >= ? AND meeting_date <= ? "
        "ORDER BY meeting_date ASC, start_time ASC",
        (start_iso, end_iso)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_meeting(meeting_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_meeting(meeting_id, title, category, meeting_date, start_time, end_time, link, attendees):
    conn = get_conn()
    conn.execute(
        "UPDATE meetings SET title=?, category=?, meeting_date=?, start_time=?, end_time=?, "
        "link=?, attendees=? WHERE id=?",
        (title, category, meeting_date, start_time, end_time, link, attendees, meeting_id)
    )
    conn.commit()
    conn.close()


def add_meeting(title, category, meeting_date, start_time, end_time, link, attendees, created_by):
    conn = get_conn()
    conn.execute(
        "INSERT INTO meetings (title, category, meeting_date, start_time, end_time, link, attendees, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, category, meeting_date, start_time, end_time, link, attendees, created_by,
         datetime.utcnow().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def delete_meeting(meeting_id):
    conn = get_conn()
    conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    conn.commit()
    conn.close()


# ============================================================================
# Holidays
# ============================================================================

def next_holiday():
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM holidays WHERE holiday_date >= ? ORDER BY holiday_date ASC LIMIT 1",
        (date.today().isoformat(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_holidays():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM holidays ORDER BY holiday_date ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_holiday(name, holiday_date):
    conn = get_conn()
    conn.execute("INSERT INTO holidays (name, holiday_date, created_at) VALUES (?, ?, ?)",
                 (name, holiday_date, datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()


def delete_holiday(holiday_id):
    conn = get_conn()
    conn.execute("DELETE FROM holidays WHERE id = ?", (holiday_id,))
    conn.commit()
    conn.close()


# ============================================================================
# Attendance punch clock (writes into ATT-001 Daily Attendance Log)
# ============================================================================

def get_today_attendance(employee_name, today_iso=None):
    today_iso = today_iso or date.today().isoformat()
    rows, _ = get_records("ATT-001", page=None)
    for r in rows:
        if (r.get("employee_name") or "").strip().lower() == employee_name.strip().lower() and r.get("date") == today_iso:
            return r
    return None


def punch_in(employee_name, created_by):
    if not employee_name:
        return None
    today_iso = date.today().isoformat()
    now_str = datetime.now().strftime("%H:%M")
    existing = get_today_attendance(employee_name, today_iso)
    if existing:
        if not existing.get("check_in"):
            set_field("ATT-001", existing["id"], "check_in", now_str)
            set_field("ATT-001", existing["id"], "status", "Present")
        return existing["id"]
    data = {"employee_name": employee_name, "date": today_iso, "check_in": now_str,
            "check_out": "", "hours_worked": "", "status": "Present", "notes": ""}
    return insert_record("ATT-001", data, created_by=created_by)


def punch_out(employee_name):
    today_iso = date.today().isoformat()
    existing = get_today_attendance(employee_name, today_iso)
    if not existing or not existing.get("check_in") or existing.get("check_out"):
        return False
    now = datetime.now()
    check_in_dt = datetime.strptime(existing["check_in"], "%H:%M")
    elapsed = (now.hour * 60 + now.minute) - (check_in_dt.hour * 60 + check_in_dt.minute)
    hours = round(max(elapsed, 0) / 60.0, 2)
    set_field("ATT-001", existing["id"], "check_out", now.strftime("%H:%M"))
    set_field("ATT-001", existing["id"], "hours_worked", hours)
    return True


# ============================================================================
# Unified pending-approvals feed
# ----------------------------------------------------------------------------
# Several forms across departments represent something waiting on a
# yes/no decision (a leave request, an IT access request, a salary
# advance...). This pulls them into one feed with an approve/reject action
# mapped per form, so the dashboards can show one actionable "Pending
# Approvals" list instead of the user hunting through each register.
# ============================================================================

APPROVAL_SOURCES = [
    {"form_code": "HR-007", "pending_status": "Pending", "approve_status": "Approved", "reject_status": "Rejected",
     "title_field": "employee_name", "meta_fmt": lambda r: "Leave · {} · {} → {}".format(
         r.get("leave_type") or "—", r.get("from_date") or "—", r.get("to_date") or "—")},
    {"form_code": "HR-006", "pending_status": "Requested", "approve_status": "Granted", "reject_status": "Revoked",
     "title_field": "employee_name", "meta_fmt": lambda r: "IT access · {}".format(r.get("systems_requested") or "—")},
    {"form_code": "PAY-003", "pending_status": "Pending", "approve_status": "Approved", "reject_status": "Rejected",
     "title_field": "employee_name", "meta_fmt": lambda r: "Salary advance · AED {:,.0f}".format(r.get("amount") or 0)},
]
APPROVAL_SOURCES_BY_FORM = {s["form_code"]: s for s in APPROVAL_SOURCES}


def pending_approvals(depts_allowed=None, limit=25):
    items = []
    for src in APPROVAL_SOURCES:
        form = FORMS_BY_CODE[src["form_code"]]
        if depts_allowed is not None and form["dept"] not in depts_allowed:
            continue
        for r in records_where_in(src["form_code"], "status", [src["pending_status"]], limit=limit):
            items.append({
                "form_code": src["form_code"],
                "record_id": r["id"],
                "doc_no": r["doc_no"],
                "title": r.get(src["title_field"]) or r["doc_no"],
                "meta": src["meta_fmt"](r),
                "created_at": r.get("created_at") or "",
            })
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items[:limit]


def resolve_approval(form_code, record_id, action):
    """action: 'approve' or 'reject'. Returns True if applied."""
    src = APPROVAL_SOURCES_BY_FORM.get(form_code)
    if not src:
        return False
    new_status = src["approve_status"] if action == "approve" else src["reject_status"]
    set_field(form_code, record_id, "status", new_status)
    return True


# ============================================================================
# Company file library - files that belong to the company rather than to one
# record. Kept in its own table so the per-record attachment queries, which the
# registers and File Manager already rely on, are untouched.
# ============================================================================

def _library_dir():
    d = os.path.join(UPLOADS_DIR, "_library")
    os.makedirs(d, exist_ok=True)
    return d


LIBRARY_FOLDERS = ["General", "Company & Licensing", "HR & Payroll", "Legal & Compliance",
                    "Property & Listings", "Finance", "Marketing", "Templates"]


def add_library_file(original_name, file_bytes, folder="General", description="", uploaded_by="Admin"):
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    stored_name = "{}.{}".format(uuid.uuid4().hex, ext) if ext else uuid.uuid4().hex
    with open(os.path.join(_library_dir(), stored_name), "wb") as fh:
        fh.write(file_bytes)
    conn = get_conn()
    conn.execute(
        "INSERT INTO library_files (original_name, stored_name, folder, description, size_bytes, uploaded_by, uploaded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (original_name, stored_name, folder, description, len(file_bytes), uploaded_by,
         datetime.utcnow().isoformat(timespec="seconds"))
    )
    conn.commit()
    conn.close()


def list_library_files(q=None, folder=None):
    conn = get_conn()
    sql = "SELECT * FROM library_files"
    where, params = [], []
    if q:
        where.append("(original_name LIKE ? OR description LIKE ?)")
        params += ["%" + q + "%", "%" + q + "%"]
    if folder:
        where.append("folder = ?")
        params.append(folder)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_library_file(file_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM library_files WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def library_file_path(rec):
    return os.path.join(_library_dir(), rec["stored_name"])


def delete_library_file(file_id):
    rec = get_library_file(file_id)
    if not rec:
        return
    try:
        path = library_file_path(rec)
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
    conn = get_conn()
    conn.execute("DELETE FROM library_files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()


# ============================================================================
# Internal chat between colleagues
# ============================================================================

def send_chat(from_user, to_user, body, kind="text", meta=None,
              attach=None):
    """Write one message. Every richer kind still lands in this one table so
    the conversation reads in order: text, file, shared record, call."""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO chat_messages (from_user, to_user, body, created_at, kind, meta, "
        "attach_name, attach_stored, attach_size) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (from_user, to_user, body, datetime.utcnow().isoformat(timespec="seconds"),
         kind, json.dumps(meta) if meta else None,
         (attach or {}).get("name"), (attach or {}).get("stored"), (attach or {}).get("size"))
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


ALLOWED_CHAT_EXTENSIONS = ALLOWED_ATTACHMENT_EXTENSIONS | {"webp", "heic", "zip", "ppt", "pptx"}
MAX_CHAT_BYTES = 20 * 1024 * 1024


def send_chat_file(from_user, to_user, file_storage, caption=""):
    """Attach a document or photo to a conversation.

    Returns (message_id, error). The same extension whitelist and size cap as
    record attachments apply, because a file dropped into chat is just as much
    company data as one attached to a record.
    """
    name = os.path.basename((file_storage.filename or "").strip())
    if not name:
        return None, "No file was chosen."
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_CHAT_EXTENSIONS:
        return None, ("That file type is not allowed here. Use "
                      + ", ".join(sorted(ALLOWED_CHAT_EXTENSIONS)) + ".")
    blob = file_storage.read()
    if not blob:
        return None, "That file is empty."
    if len(blob) > MAX_CHAT_BYTES:
        return None, "That file is larger than 20 MB. Send a smaller copy."
    stored = "{}.{}".format(uuid.uuid4().hex, ext)
    with open(os.path.join(CHAT_DIR, stored), "wb") as fh:
        fh.write(blob)
    mid = send_chat(from_user, to_user, caption or name, kind="file",
                    attach={"name": name, "stored": stored, "size": len(blob)})
    return mid, None


def chat_file_path(msg):
    """Resolve an attachment, refusing anything that escapes the chat folder."""
    stored = msg.get("attach_stored") if isinstance(msg, dict) else msg["attach_stored"]
    if not stored:
        return None
    path = os.path.realpath(os.path.join(CHAT_DIR, stored))
    root = os.path.realpath(CHAT_DIR)
    if not (path == root or path.startswith(root + os.sep)):
        return None
    return path if os.path.exists(path) else None


def get_chat_message(message_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def chat_thread(user_a, user_b, limit=200):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?) "
        "ORDER BY id ASC LIMIT ?",
        (user_a, user_b, user_b, user_a, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_chat_read(reader, other):
    conn = get_conn()
    conn.execute(
        "UPDATE chat_messages SET read_at = ? WHERE to_user = ? AND from_user = ? AND read_at IS NULL",
        (datetime.utcnow().isoformat(timespec="seconds"), reader, other)
    )
    conn.commit()
    conn.close()


def chat_overview(username):
    """Per-colleague last message, timestamp and unread count - the left rail."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM chat_messages WHERE from_user = ? OR to_user = ? ORDER BY id ASC",
        (username, username)
    ).fetchall()
    conn.close()
    latest, unread = {}, {}
    for r in rows:
        other = r["to_user"] if r["from_user"] == username else r["from_user"]
        latest[other] = dict(r)
        if r["to_user"] == username and not r["read_at"]:
            unread[other] = unread.get(other, 0) + 1
    return latest, unread


def chat_unread_total(username):
    conn = get_conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM chat_messages WHERE to_user = ? AND read_at IS NULL", (username,)
    ).fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------- live calls --
# A call has two halves. This table is the live session - who rang whom, which
# room, when it was answered, when it ended. When the call finishes the details
# are written once into the SAL-009 Call Log register, which is the permanent
# record. The session row stays as the link between the two.

CALL_STATUS_RINGING = "ringing"
CALL_STATUS_LIVE = "live"
CALL_STATUS_ENDED = "ended"
CALL_STATUS_MISSED = "missed"


def _room_name(seed):
    """A room name nobody can guess. The room is the only thing protecting the
    call, so it is a long random token, never the two usernames."""
    return "dharani360-" + hashlib.sha256(
        (seed + "|" + uuid.uuid4().hex).encode("utf-8")).hexdigest()[:26]


MEETING_HOSTS = (
    "meet.google.com", "zoom.us", "teams.microsoft.com", "teams.live.com",
    "webex.com", "whereby.com", "meet.jit.si",
)


def normalise_meeting_link(raw):
    """Accept a meeting link, or say why it was refused.

    Only real meeting providers are allowed. The link is opened for staff and
    for guests, so letting any address through would turn this field into a
    way to push arbitrary links at people through a trusted screen.
    Returns (url, error).
    """
    from urllib.parse import urlparse
    raw = (raw or "").strip()
    if not raw:
        return "", None
    if not raw.lower().startswith(("http://", "https://")):
        raw = "https://" + raw
    try:
        parts = urlparse(raw)
    except ValueError:
        return None, "That does not look like a web address."
    host = (parts.hostname or "").lower()
    if not host:
        return None, "That does not look like a web address."
    if not any(host == h or host.endswith("." + h) for h in MEETING_HOSTS):
        return None, ("Use a meeting link from Google Meet, Zoom, Microsoft Teams, "
                      "Webex or Whereby. That address is not one of them.")
    return parts._replace(scheme="https").geturl(), None


def start_call(started_by, other_user=None, contact_name=None, contact_number=None,
               mode="video", subject="", meeting_url=""):
    """Open a call session and return the full row."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    room = _room_name("{}|{}|{}".format(started_by, other_user or contact_name or "guest", now))
    token = uuid.uuid4().hex[:20]
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO call_sessions (room, mode, started_by, other_user, contact_name, "
        "contact_number, guest_token, subject, started_at, status, meeting_url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (room, mode, started_by, other_user, contact_name, contact_number, token,
         subject, now, CALL_STATUS_RINGING if other_user else CALL_STATUS_LIVE,
         meeting_url or None))
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return get_call(cid)


def get_call(call_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM call_sessions WHERE id = ?", (call_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_call_by_token(token):
    if not token:
        return None
    conn = get_conn()
    row = conn.execute("SELECT * FROM call_sessions WHERE guest_token = ?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def answer_call(call_id):
    conn = get_conn()
    conn.execute("UPDATE call_sessions SET status = ?, answered_at = COALESCE(answered_at, ?) "
                 "WHERE id = ? AND status IN (?, ?)",
                 (CALL_STATUS_LIVE, datetime.utcnow().isoformat(timespec="seconds"),
                  call_id, CALL_STATUS_RINGING, CALL_STATUS_LIVE))
    conn.commit()
    conn.close()
    return get_call(call_id)


def end_call(call_id, seconds=None, outcome="", status=None):
    """Close the session. Duration is taken from the browser when it is given,
    otherwise measured from the timestamps, so a closed laptop still logs."""
    call = get_call(call_id)
    if not call or call["status"] == CALL_STATUS_ENDED:
        return call
    now = datetime.utcnow()
    if seconds is None:
        base = call["answered_at"] or call["started_at"]
        try:
            seconds = int((now - datetime.fromisoformat(base)).total_seconds())
        except (TypeError, ValueError):
            seconds = 0
    seconds = max(0, min(int(seconds or 0), 60 * 60 * 12))
    # The video happens in Google Meet or Zoom, so this system cannot see
    # whether anyone spoke. Two things stand in for that: the other person
    # opening the call screen, and the caller having stayed on the line long
    # enough for it to have been a real conversation. Without the second test
    # every call to a client came out as "Missed", which is worse than useless
    # in a register somebody may later have to rely on.
    ANSWERED_AFTER = 15          # seconds
    really_happened = bool(call["answered_at"]) or seconds >= ANSWERED_AFTER
    final = status or (CALL_STATUS_ENDED if really_happened else CALL_STATUS_MISSED)
    conn = get_conn()
    conn.execute("UPDATE call_sessions SET status = ?, ended_at = ?, duration_seconds = ?, "
                 "outcome = ? WHERE id = ?",
                 (final, now.isoformat(timespec="seconds"), seconds, outcome, call_id))
    conn.commit()
    conn.close()
    return get_call(call_id)


def attach_call_record(call_id, record_id):
    conn = get_conn()
    conn.execute("UPDATE call_sessions SET record_id = ? WHERE id = ?", (record_id, call_id))
    conn.commit()
    conn.close()


def incoming_calls_for(username, max_age_seconds=75):
    """Calls ringing this person right now. Anything older than about a minute
    has stopped ringing in real life, so it is not shown as live."""
    cutoff = (datetime.utcnow() - timedelta(seconds=max_age_seconds)).isoformat(timespec="seconds")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM call_sessions WHERE other_user = ? AND status = ? AND started_at >= ? "
        "ORDER BY id DESC LIMIT 3", (username, CALL_STATUS_RINGING, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def expire_stale_calls(max_age_seconds=90):
    """A call nobody answered becomes a missed call rather than ringing forever."""
    cutoff = (datetime.utcnow() - timedelta(seconds=max_age_seconds)).isoformat(timespec="seconds")
    conn = get_conn()
    rows = conn.execute("SELECT id FROM call_sessions WHERE status = ? AND started_at < ?",
                        (CALL_STATUS_RINGING, cutoff)).fetchall()
    conn.close()
    for r in rows:
        end_call(r["id"], seconds=0, status=CALL_STATUS_MISSED)
    return len(rows)


def recent_calls_with(username, other, limit=6):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM call_sessions WHERE (started_by = ? AND other_user = ?) "
        "OR (started_by = ? AND other_user = ?) ORDER BY id DESC LIMIT ?",
        (username, other, other, username, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_calls_for(contact_name):
    """How many calls are logged against this person in the Call Log."""
    if not contact_name:
        return 0
    conn = get_conn()
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM {} WHERE contact_name = ?".format(table_name("SAL-009")),
            (contact_name,)
        ).fetchone()[0]
    except sqlite3.Error:
        n = 0
    conn.close()
    return n
