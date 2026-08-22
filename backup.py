# -*- coding: utf-8 -*-
"""
DHARANI 360 - backup and restore
=================================
A backup nobody has restored is not a backup. This script does both, and
the `verify` command proves the backup is readable before you trust it.

    python backup.py create            make a new backup
    python backup.py create --to D:\\  also copy it somewhere off this disk
    python backup.py list              show what backups exist
    python backup.py verify <file>     restore into a scratch copy and check it
    python backup.py restore <file>    replace the live data (asks first)

A backup sitting on the same disk as the database is not a backup - the two
are lost together. Give `create` a --to path on a different drive, a network
share, or a synced folder (OneDrive, Dropbox, Google Drive) and the archive
is copied there as well. Set COPY_TO in .env to do it every time without
having to remember the flag.

What a backup contains:

  * the database - the SQLite file, or a pg_dump when DATABASE_URL is set
  * instance/uploads   - every attachment on every record
  * instance/photos    - staff photographs
  * instance/chatfiles - files sent in chat
  * instance/library   - the company file library

The signing key (instance/secret_key) is deliberately NOT included: it is a
credential, not data, and a backup file often travels further than it should.
Losing it signs everyone out; it does not lose a single record.

Automating it on Windows: Task Scheduler -> Create Basic Task -> Daily ->
Start a program -> backup.bat in this folder.
On Linux/Mac, a cron line: 0 2 * * * cd /path/to/portal && python backup.py create
"""
import config  # noqa: F401  - must be first: loads .env into the environment
import os
import sys
import shutil
import zipfile
import subprocess
import tempfile
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
BACKUP_DIR = os.environ.get("BACKUP_DIR") or os.path.join(BASE_DIR, "backups")
DB_FILE = os.path.join(INSTANCE_DIR, "dharani360.db")
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

#: Backups older than this are removed by `create`. Set KEEP_DAYS to change it.
KEEP_DAYS = int(os.environ.get("KEEP_DAYS") or 30)

#: A second location every backup is copied to - another drive, a network
#: share, or a synced folder. This is what makes it a real backup rather than
#: a second file on the disk that is about to fail.
COPY_TO = (os.environ.get("COPY_TO") or "").strip()

FILE_FOLDERS = ["uploads", "photos", "chatfiles", "library"]
DUMP_NAME = "database.sql"
SQLITE_NAME = "dharani360.db"


def _say(msg=""):
    print(msg, flush=True)


def _stamp():
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------

def _dump_postgres(target_path):
    """pg_dump the whole database into target_path."""
    if shutil.which("pg_dump") is None:
        raise RuntimeError(
            "pg_dump was not found on this machine. It ships with the "
            "PostgreSQL client tools - install those, or run this script "
            "somewhere that has them.")
    with open(target_path, "wb") as fh:
        proc = subprocess.run(["pg_dump", "--no-owner", "--no-privileges", DATABASE_URL],
                              stdout=fh, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError("pg_dump failed: {}".format(proc.stderr.decode("utf-8", "replace")[:500]))


def _copy_sqlite(target_path):
    """Copy the SQLite file safely, even while the app is running."""
    import sqlite3
    if not os.path.exists(DB_FILE):
        raise RuntimeError("No database found at {}. Has the app been run yet?".format(DB_FILE))
    src = sqlite3.connect(DB_FILE)
    dst = sqlite3.connect(target_path)
    try:
        # The backup API takes a consistent snapshot without stopping the app.
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _copy_offsite(path, destination):
    """Put a second copy somewhere that is not this disk."""
    if not destination:
        return None
    try:
        os.makedirs(destination, exist_ok=True)
        target = os.path.join(destination, os.path.basename(path))
        shutil.copy2(path, target)
        _say("  Copied to {}".format(target))
        return target
    except OSError as exc:
        # A failed off-site copy must be loud: a backup you believe exists
        # and does not is worse than no backup at all.
        _say("  !  COULD NOT COPY to {} ({}).".format(destination, exc))
        _say("     The local backup was still written, but it is on the same")
        _say("     disk as your data. Fix the destination and run this again.")
        return None


def create(copy_to=None):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    name = "dharani360-{}-{}.zip".format("pg" if IS_POSTGRES else "sqlite", _stamp())
    path = os.path.join(BACKUP_DIR, name)

    _say("Backing up {}".format("PostgreSQL" if IS_POSTGRES else "SQLite"))
    scratch = tempfile.mkdtemp(prefix="d360-backup-")
    try:
        if IS_POSTGRES:
            db_path = os.path.join(scratch, DUMP_NAME)
            _dump_postgres(db_path)
        else:
            db_path = os.path.join(scratch, SQLITE_NAME)
            _copy_sqlite(db_path)
        _say("  database   {:,} bytes".format(os.path.getsize(db_path)))

        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(db_path, os.path.basename(db_path))
            for folder in FILE_FOLDERS:
                src = os.path.join(INSTANCE_DIR, folder)
                if not os.path.isdir(src):
                    continue
                count = 0
                for root, _dirs, files in os.walk(src):
                    for fname in files:
                        full = os.path.join(root, fname)
                        rel = os.path.relpath(full, INSTANCE_DIR)
                        z.write(full, os.path.join("instance", rel))
                        count += 1
                if count:
                    _say("  {:<10} {:,} files".format(folder, count))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    _say("\nWrote {} ({:,} bytes)".format(path, os.path.getsize(path)))

    destination = copy_to or COPY_TO
    if destination:
        _copy_offsite(path, destination)
    else:
        _say("  Note: this copy is on the same disk as your data. Use --to, or")
        _say("        set COPY_TO in .env, to keep a copy somewhere safer.")

    _prune()
    _say("\nNow prove it works:  python backup.py verify \"{}\"".format(path))
    return path


def _prune():
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    removed = 0
    for name in os.listdir(BACKUP_DIR):
        if not name.endswith(".zip"):
            continue
        full = os.path.join(BACKUP_DIR, name)
        if datetime.fromtimestamp(os.path.getmtime(full)) < cutoff:
            os.remove(full)
            removed += 1
    if removed:
        _say("Removed {} backup(s) older than {} days.".format(removed, KEEP_DAYS))


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def list_backups():
    if not os.path.isdir(BACKUP_DIR):
        _say("No backups yet. Run:  python backup.py create")
        return
    names = sorted((n for n in os.listdir(BACKUP_DIR) if n.endswith(".zip")), reverse=True)
    if not names:
        _say("No backups yet. Run:  python backup.py create")
        return
    _say("{:<44} {:>12}  {}".format("Backup", "Size", "Made"))
    for name in names:
        full = os.path.join(BACKUP_DIR, name)
        _say("{:<44} {:>12,}  {}".format(
            name, os.path.getsize(full),
            datetime.fromtimestamp(os.path.getmtime(full)).strftime("%d %b %Y %H:%M")))
    _say("\n{} backup(s) in {}".format(len(names), BACKUP_DIR))


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

def verify(archive):
    """Open the backup, restore the database into a scratch copy, count rows.

    Nothing live is touched. This is the drill that turns "we have backups"
    into "we know our backups work".
    """
    if not os.path.exists(archive):
        _say("No such file: {}".format(archive))
        return 1

    _say("Verifying {}".format(archive))
    scratch = tempfile.mkdtemp(prefix="d360-verify-")
    try:
        with zipfile.ZipFile(archive) as z:
            bad = z.testzip()
            if bad:
                _say("  FAIL  the archive is corrupt at {}".format(bad))
                return 1
            names = z.namelist()
            z.extractall(scratch)
        _say("  ok    archive opens, {} entries".format(len(names)))

        attachments = [n for n in names if n.startswith("instance/")]
        _say("  ok    {} attached file(s) included".format(len(attachments)))

        sqlite_path = os.path.join(scratch, SQLITE_NAME)
        dump_path = os.path.join(scratch, DUMP_NAME)

        if os.path.exists(sqlite_path):
            import sqlite3
            conn = sqlite3.connect(sqlite_path)
            conn.row_factory = sqlite3.Row
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            try:
                audit = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            except sqlite3.Error:
                audit = 0
            records = 0
            for t in tables:
                if t.upper().startswith("FRM_"):
                    records += conn.execute("SELECT COUNT(*) FROM {}".format(t)).fetchone()[0]
            conn.close()
            _say("  ok    database restores: {} tables, {:,} register record(s), "
                 "{} user(s), {} audit entries"
                 .format(len(tables), records, users, audit))
            if users == 0:
                _say("  FAIL  no user accounts in the backup - it would not be usable")
                return 1
        elif os.path.exists(dump_path):
            size = os.path.getsize(dump_path)
            with open(dump_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            _say("  ok    pg_dump present, {:,} bytes".format(size))
            for needed in ("CREATE TABLE", "users", "audit_log"):
                if needed not in text:
                    _say("  FAIL  the dump does not mention {}".format(needed))
                    return 1
            _say("  ok    the dump contains the schema, users and audit_log")
            _say("        (a full restore drill needs a scratch Postgres database:")
            _say("         createdb d360_drill && psql d360_drill < {})".format(DUMP_NAME))
        else:
            _say("  FAIL  the archive contains no database")
            return 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    _say("\nThis backup is good.")
    return 0


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------

def restore(archive, assume_yes=False):
    if not os.path.exists(archive):
        _say("No such file: {}".format(archive))
        return 1

    _say("RESTORE will replace the current data with the contents of:")
    _say("   {}".format(archive))
    _say("")
    _say("Everything entered since that backup was taken will be lost.")
    if not assume_yes:
        answer = input('Type the word RESTORE to continue: ').strip()
        if answer != "RESTORE":
            _say("Nothing was changed.")
            return 1

    # Always take a safety copy of what is about to be overwritten.
    if os.path.exists(DB_FILE) or IS_POSTGRES:
        _say("\nTaking a safety backup of the current data first...")
        try:
            create()
        except Exception as exc:  # a failed safety copy must stop the restore
            _say("Could not back up the current data ({}), so the restore was "
                 "stopped. Fix that first.".format(exc))
            return 1

    scratch = tempfile.mkdtemp(prefix="d360-restore-")
    try:
        with zipfile.ZipFile(archive) as z:
            z.extractall(scratch)

        sqlite_path = os.path.join(scratch, SQLITE_NAME)
        dump_path = os.path.join(scratch, DUMP_NAME)

        if os.path.exists(sqlite_path):
            os.makedirs(INSTANCE_DIR, exist_ok=True)
            shutil.copy2(sqlite_path, DB_FILE)
            _say("Database restored to {}".format(DB_FILE))
        elif os.path.exists(dump_path):
            if shutil.which("psql") is None:
                _say("psql was not found, so the Postgres dump cannot be loaded here.")
                return 1
            proc = subprocess.run(["psql", DATABASE_URL, "-v", "ON_ERROR_STOP=1",
                                   "-f", dump_path], stderr=subprocess.PIPE)
            if proc.returncode != 0:
                _say("psql failed: {}".format(proc.stderr.decode("utf-8", "replace")[:800]))
                return 1
            _say("Database restored into {}".format(DATABASE_URL.split("@")[-1]))
        else:
            _say("The archive contains no database.")
            return 1

        src_instance = os.path.join(scratch, "instance")
        if os.path.isdir(src_instance):
            for folder in FILE_FOLDERS:
                src = os.path.join(src_instance, folder)
                if not os.path.isdir(src):
                    continue
                dst = os.path.join(INSTANCE_DIR, folder)
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
                _say("Restored instance/{}".format(folder))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    _say("\nRestore complete. Start the portal and check a few records.")
    return 0


# ---------------------------------------------------------------------------

USAGE = __doc__.split("What a backup contains")[0].strip()


def main(argv):
    if len(argv) < 2:
        _say(USAGE)
        return 1
    cmd = argv[1].lower()
    if cmd == "create":
        copy_to = None
        if "--to" in argv:
            i = argv.index("--to")
            if i + 1 < len(argv):
                copy_to = argv[i + 1]
            else:
                _say("Usage: python backup.py create --to <folder>")
                return 1
        create(copy_to=copy_to)
        return 0
    if cmd == "list":
        list_backups()
        return 0
    if cmd == "verify":
        if len(argv) < 3:
            _say("Usage: python backup.py verify <backup.zip>")
            return 1
        return verify(argv[2])
    if cmd == "restore":
        if len(argv) < 3:
            _say("Usage: python backup.py restore <backup.zip>")
            return 1
        return restore(argv[2], assume_yes="--yes" in argv)
    _say(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
