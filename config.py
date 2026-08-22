# -*- coding: utf-8 -*-
"""
DHARANI 360 - Configuration
============================
One place that knows every setting, where it came from, and what happens if
it is missing. Import this before anything else - it loads the .env file, so
every other module can read os.environ and get the right answer.

Settings are read in this order, first match wins:

  1. A real environment variable  (how a hosted deployment is configured)
  2. The .env file next to this one  (how a local machine is configured)
  3. A safe default  (how a fresh install still starts)

Nothing secret is ever committed. `.env` is in .gitignore; `.env.example`
lists every setting with a description and no real values.

To see what this installation is actually using:

    python config.py

It prints every setting, where each one came from, and masks the secrets.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

#: Filled in by load_env(): which settings came from the .env file rather
#: than from the real environment. Only used by the report below.
_FROM_FILE = set()


def load_env(path=ENV_PATH):
    """Read .env into os.environ without overwriting anything already set.

    Deliberately hand-rolled rather than a dependency: the format is three
    lines of parsing, and one less package to install is one less thing to
    go wrong on a client's machine.

    Supported:  KEY=value, KEY="value with spaces", # comments, blank lines,
                and a leading "export " which people paste out of habit.

    Two rules that are easy to get wrong and painful in production:

      * A key that appears twice in the file takes its LAST value, which is
        what people expect when they paste a correction at the bottom rather
        than editing the line above.
      * An environment variable that exists but is EMPTY does not count as
        set. Hosting panels routinely create blank variables, and a blank
        one silently overriding a correct .env value is a bad afternoon.
    """
    if not os.path.exists(path):
        return 0

    parsed = {}
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key:
                parsed[key] = value        # last one wins

    loaded = 0
    for key, value in parsed.items():
        if os.environ.get(key):            # a real, non-empty variable wins
            continue
        os.environ[key] = value
        _FROM_FILE.add(key)
        loaded += 1
    return loaded


load_env()


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def get(name, default=None):
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def flag(name, default=False):
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def number(name, default):
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# The settings themselves
# ---------------------------------------------------------------------------

#: Signs session cookies. Without it, app.py generates one and keeps it in
#: instance/secret_key. A hosted deployment must set it, or everyone is
#: signed out whenever the service restarts.
SECRET_KEY = get("SECRET_KEY")

#: Empty  -> SQLite at instance/dharani360.db (a single PC).
#: Set    -> PostgreSQL (a real server, several people at once).
DATABASE_URL = get("DATABASE_URL", "")

#: Supabase, used for sign-in and - once configured - for attachment storage.
SUPABASE_URL = get("SUPABASE_URL")
SUPABASE_ANON_KEY = get("SUPABASE_ANON_KEY")
SUPABASE_BUCKET = get("SUPABASE_BUCKET", "dharani360-files")

#: Who may sign in. Comma-separated. Empty means "fall back to the list in
#: supabase_auth.py", so an existing install keeps working untouched.
ALLOWED_EMAILS = [e.strip().lower() for e in (get("ALLOWED_EMAILS", "") or "").split(",") if e.strip()]

#: Security. SECURE_COOKIES defaults to on when the app looks hosted.
SECURE_COOKIES = get("SECURE_COOKIES")          # None = decide automatically
SESSION_HOURS = number("SESSION_HOURS", 12)

#: Web server. More than one worker is only safe on Postgres.
PORT = number("PORT", 5000)
GUNICORN_WORKERS = number("GUNICORN_WORKERS", 1)

#: Backups.
BACKUP_DIR = get("BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
KEEP_DAYS = number("KEEP_DAYS", 30)

#: Outgoing email for the daily compliance digest. Stored in the database
#: today via the Settings page; these override it when hosted.
SMTP_HOST = get("SMTP_HOST")
SMTP_PORT = number("SMTP_PORT", 587)
SMTP_USER = get("SMTP_USER")
SMTP_PASSWORD = get("SMTP_PASSWORD")
DIGEST_FROM = get("DIGEST_FROM")
DIGEST_TO = get("DIGEST_TO")

#: Marks the demo deployment, which re-seeds sample data on every start.
DEMO_MODE = flag("DEMO_MODE", False)

#: Set only by preview.py. Signs the viewer in automatically and puts a
#: PREVIEW banner on every page. Never set this on a real installation - the
#: guard in app.py additionally refuses it for anything but a local request,
#: but the setting itself should not exist outside a preview.
PREVIEW = flag("D360_PREVIEW", False)


def is_hosted():
    """True when this process is a deployed service rather than a desk PC."""
    return bool(DATABASE_URL or SECRET_KEY)


def database_engine():
    return "postgres" if DATABASE_URL.startswith(("postgres://", "postgresql://")) else "sqlite"


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------

SECRET_SETTINGS = {"SECRET_KEY", "SUPABASE_ANON_KEY", "SMTP_PASSWORD", "DATABASE_URL"}

REPORTED = [
    ("DATABASE_URL", DATABASE_URL, "Empty = SQLite on this PC. Set = PostgreSQL."),
    ("SECRET_KEY", SECRET_KEY, "Signs login cookies. Required when hosted."),
    ("SUPABASE_URL", SUPABASE_URL, "Supabase project used for sign-in."),
    ("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY, "Publishable key. Never the service_role key."),
    ("SUPABASE_BUCKET", SUPABASE_BUCKET, "Storage bucket for attachments."),
    ("ALLOWED_EMAILS", ",".join(ALLOWED_EMAILS), "Who may sign in. Empty = the list in supabase_auth.py."),
    ("SECURE_COOKIES", SECURE_COOKIES, "Empty = on when hosted, off on a local PC."),
    ("SESSION_HOURS", SESSION_HOURS, "How long a sign-in lasts."),
    ("GUNICORN_WORKERS", GUNICORN_WORKERS, "Keep at 1 on SQLite. Raise on Postgres."),
    ("PORT", PORT, "Port the web server listens on."),
    ("BACKUP_DIR", BACKUP_DIR, "Where backups are written."),
    ("KEEP_DAYS", KEEP_DAYS, "How long backups are kept."),
    ("SMTP_HOST", SMTP_HOST, "Outgoing mail server for the daily digest."),
    ("SMTP_USER", SMTP_USER, "Mail account used to send."),
    ("SMTP_PASSWORD", SMTP_PASSWORD, "App password for that account."),
    ("DIGEST_FROM", DIGEST_FROM, "Address the digest is sent from."),
    ("DIGEST_TO", DIGEST_TO, "Address the digest is sent to."),
    ("DEMO_MODE", DEMO_MODE, "Re-seeds sample data on every start."),
    ("D360_PREVIEW", PREVIEW, "Preview mode: auto sign-in, sample data, local only."),
]


def mask(name, value):
    if value in (None, "", False):
        return "(not set)"
    text = str(value)
    if name not in SECRET_SETTINGS:
        return text
    if name == "DATABASE_URL":
        import re
        return re.sub(r"//[^@/]*@", "//***:***@", text)
    if len(text) <= 8:
        return "***"
    return text[:4] + "..." + text[-4:]


def source(name):
    if name in _FROM_FILE:
        return ".env"
    if os.environ.get(name):
        return "environment"
    return "default"


def report():
    print("DHARANI 360 configuration")
    print("=" * 74)
    print("{:<20} {:<26} {:<12}".format("Setting", "Value", "From"))
    print("-" * 74)
    for name, value, _desc in REPORTED:
        print("{:<20} {:<26} {:<12}".format(name, mask(name, value)[:26], source(name)))
    print("-" * 74)
    print()
    print("  .env file      {}".format(ENV_PATH if os.path.exists(ENV_PATH) else "(none - using defaults)"))
    print("  Database       {}".format(database_engine()))
    print("  Looks hosted   {}".format("yes" if is_hosted() else "no - running as a local tool"))
    print()

    problems = []
    if is_hosted() and not SECRET_KEY:
        problems.append("Hosted but SECRET_KEY is not set - everyone is signed out on every restart.")
    if database_engine() == "sqlite" and GUNICORN_WORKERS > 1:
        problems.append("GUNICORN_WORKERS is above 1 on SQLite - several processes writing one "
                        "file will corrupt it. Set it to 1, or move to Postgres.")
    if SUPABASE_URL and not SUPABASE_ANON_KEY:
        problems.append("SUPABASE_URL is set but SUPABASE_ANON_KEY is not - sign-in will fail.")
    if SUPABASE_ANON_KEY and "service_role" in str(SUPABASE_ANON_KEY):
        problems.append("SUPABASE_ANON_KEY looks like a service_role key. Never use that here - "
                        "it bypasses every security rule. Use the publishable/anon key.")
    if PREVIEW and DATABASE_URL:
        problems.append("Preview mode is on AND a DATABASE_URL is set. Preview must never "
                        "reach a real database - start it with preview.py, which isolates it.")
    if not DATABASE_URL and is_hosted():
        problems.append("Hosted with no DATABASE_URL - records will be written to a file that "
                        "the host may erase on the next deploy.")

    if problems:
        print("Problems found:")
        for p in problems:
            print("  !  {}".format(p))
        print()
        return 1
    print("No problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(report())
