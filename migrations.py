# -*- coding: utf-8 -*-
"""
DHARANI 360 - Schema versioning
================================
    python migrations.py status     what the database looks like right now
    python migrations.py check      exit non-zero if changes are pending
    python migrations.py upgrade    apply them

Why this and not Alembic
------------------------
Alembic is the right answer when your schema is written by hand. Here it is
not: 112 of the tables are generated from `forms_data.py`, and adding a form
is meant to be one dictionary entry with no migration to write. Alembic's
autogenerate needs SQLAlchemy models for every table, so adopting it would
mean hand-maintaining 112 models that already exist as metadata - defeating
the design that makes this system fast to extend.

So the schema is versioned in two halves, each the right way for its half:

  * **System tables** (users, audit_log, settings, chat, calls...) change
    rarely and deliberately. Each change is a numbered migration below, run
    once, in order, and recorded in `schema_migrations`. That is what Alembic
    would have given us, without the dependency or the 112 fake models.

  * **Register tables** are generated from `forms_data.py` and reconciled on
    every start. New form -> new table. New field -> new column.

The rule that matters: **this never drops anything.** If a field disappears
from `forms_data.py`, the column stays and is reported as an orphan. A
compliance system silently deleting a column of real records because someone
tidied a Python file is not a trade worth making.
"""
import config  # noqa: F401  - must be first: loads .env into the environment
import sys
from datetime import datetime

import dbcompat


# ---------------------------------------------------------------------------
# The migration list
# ---------------------------------------------------------------------------
# Add a new step by appending to this list. Never edit or renumber a step that
# has shipped - a database that already ran it will not run it again, so an
# edited step silently means two installations have different schemas.

def _m001_baseline(conn):
    """Everything created by db.init_db() up to this point.

    Recorded rather than executed: init_db() is idempotent and already built
    these tables, so this step exists to mark the starting line.
    """
    return "baseline recorded"


def _m002_audit_and_throttling(conn):
    """audit_log and login_attempts, added when the system became multi-user."""
    return "audit_log and login_attempts present"


MIGRATIONS = [
    (1, "baseline", _m001_baseline),
    (2, "audit trail and sign-in throttling", _m002_audit_and_throttling),
]


# ---------------------------------------------------------------------------
# Bookkeeping
# ---------------------------------------------------------------------------

def ensure_version_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        applied_at TEXT NOT NULL
    )""")
    conn.commit()


def applied_versions(conn):
    ensure_version_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return {r[0] for r in rows}


def pending(conn):
    done = applied_versions(conn)
    return [(v, name, fn) for (v, name, fn) in MIGRATIONS if v not in done]


def apply_pending(conn, log=None):
    """Run every migration that has not run here yet, in order."""
    applied = []
    for version, name, fn in pending(conn):
        detail = fn(conn)
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, datetime.utcnow().isoformat(timespec="seconds")))
        conn.commit()
        applied.append((version, name, detail))
        if log:
            log("  applied {:03d}  {}".format(version, name))
    return applied


# ---------------------------------------------------------------------------
# Register tables, reconciled against forms_data.py
# ---------------------------------------------------------------------------

def register_drift(conn):
    """What differs between forms_data.py and the database, without changing it.

    Returns {"missing_tables": [...], "missing_columns": [(table, column)],
             "orphan_columns": [(table, column)]}.

    Orphan columns are the interesting ones: a field that used to exist and
    still holds data, but is no longer in forms_data.py. Nothing removes them.
    """
    from forms_data import FORMS, table_name

    cur = conn.cursor()
    missing_tables, missing_columns, orphan_columns = [], [], []

    base_columns = {"id", "doc_no", "created_at", "updated_at",
                    "created_by", "status", "notes"}

    for form in FORMS:
        tname = table_name(form["code"])
        try:
            existing = dbcompat.table_columns(cur, tname)
        except dbcompat.DBError:
            existing = set()
        if not existing:
            missing_tables.append(tname)
            continue

        wanted = {f["name"] for f in form["fields"]}
        for name in sorted(wanted - existing):
            missing_columns.append((tname, name))
        for name in sorted(existing - wanted - base_columns):
            orphan_columns.append((tname, name))

    return {"missing_tables": missing_tables,
            "missing_columns": missing_columns,
            "orphan_columns": orphan_columns}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _say(msg=""):
    print(msg, flush=True)


def status():
    import db
    conn = db.get_conn()
    try:
        done = applied_versions(conn)
        todo = pending(conn)
        drift = register_drift(conn)

        _say("DHARANI 360 schema")
        _say("=" * 66)
        _say("  Engine            {}".format(dbcompat.describe()))
        _say()
        _say("  System tables")
        for version, name, _fn in MIGRATIONS:
            mark = "applied" if version in done else "PENDING"
            _say("    {:03d}  {:<38} {}".format(version, name[:38], mark))
        _say()
        _say("  Registers ({} defined in forms_data.py)".format(
            len(__import__("forms_data").FORMS)))
        _say("    tables to create   {}".format(len(drift["missing_tables"])))
        _say("    columns to add     {}".format(len(drift["missing_columns"])))
        _say("    orphan columns     {}".format(len(drift["orphan_columns"])))

        if drift["missing_tables"]:
            _say()
            _say("  Will be created on next start:")
            for t in drift["missing_tables"][:10]:
                _say("    + {}".format(t))
            if len(drift["missing_tables"]) > 10:
                _say("    ... and {} more".format(len(drift["missing_tables"]) - 10))

        if drift["missing_columns"]:
            _say()
            _say("  Will be added on next start:")
            for t, c in drift["missing_columns"][:10]:
                _say("    + {}.{}".format(t, c))
            if len(drift["missing_columns"]) > 10:
                _say("    ... and {} more".format(len(drift["missing_columns"]) - 10))

        if drift["orphan_columns"]:
            _say()
            _say("  Orphan columns - in the database, not in forms_data.py.")
            _say("  These are NOT removed. They may still hold real records.")
            for t, c in drift["orphan_columns"][:15]:
                _say("    ? {}.{}".format(t, c))
            if len(drift["orphan_columns"]) > 15:
                _say("    ... and {} more".format(len(drift["orphan_columns"]) - 15))

        _say()
        if todo or drift["missing_tables"] or drift["missing_columns"]:
            _say("  Changes are pending. Back up first, then: python migrations.py upgrade")
            return 1
        _say("  Up to date.")
        return 0
    finally:
        conn.close()


def check():
    """For CI and deploy scripts: non-zero means the schema would change."""
    import db
    conn = db.get_conn()
    try:
        todo = pending(conn)
        drift = register_drift(conn)
        changes = (len(todo) + len(drift["missing_tables"]) + len(drift["missing_columns"]))
        if changes:
            _say("{} schema change(s) pending. Run: python migrations.py upgrade".format(changes))
            return 1
        _say("Schema is up to date.")
        return 0
    finally:
        conn.close()


def upgrade():
    """Apply system migrations, then let db.init_db() reconcile the registers."""
    import db
    _say("Applying schema changes to {}".format(dbcompat.describe()))
    _say()
    _say("  Take a backup first if you have not:  python backup.py create")
    _say()

    conn = db.get_conn()
    try:
        applied = apply_pending(conn, log=_say)
        if not applied:
            _say("  system tables already up to date")
    finally:
        conn.close()

    before = register_drift(db.get_conn())
    db.init_db()
    after = register_drift(db.get_conn())

    created = len(before["missing_tables"]) - len(after["missing_tables"])
    added = len(before["missing_columns"]) - len(after["missing_columns"])
    _say("  registers: {} table(s) created, {} column(s) added".format(created, added))

    if after["orphan_columns"]:
        _say()
        _say("  {} orphan column(s) left in place - see: python migrations.py status"
             .format(len(after["orphan_columns"])))
    _say()
    _say("Done.")
    return 0


USAGE = "Usage: python migrations.py [status|check|upgrade]"


def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "status").lower()
    if cmd == "status":
        return status()
    if cmd == "check":
        return check()
    if cmd == "upgrade":
        return upgrade()
    _say(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
