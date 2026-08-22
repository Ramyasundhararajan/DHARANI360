# -*- coding: utf-8 -*-
"""
DHARANI 360 - Database compatibility layer
===========================================
Lets the whole application run unchanged on either:

  * SQLite   - the default. One file, no server, perfect for a single PC.
  * Postgres - set DATABASE_URL and it switches. Needed the moment more
               than one person uses the system at the same time.

Nothing else in the codebase needs to know which one is in use. db.py keeps
writing plain SQLite-flavoured SQL with "?" placeholders; this module
translates it on the way to the server when the server is Postgres.

Switch by setting one environment variable:

    DATABASE_URL=postgresql://user:password@host:5432/dharani360

Leave it unset and everything behaves exactly as it did before.
"""
import config  # noqa: F401  - must be first: loads .env into the environment
import os
import re
import sqlite3

DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

# Name of the case-insensitive collation we create on Postgres so that
# SQLite's "COLLATE NOCASE" keeps meaning what it means today.
CI_COLLATION = "d360_ci"

_pg = None
if IS_POSTGRES:  # imported lazily so SQLite installs need no driver
    import psycopg
    from psycopg import sql as _pgsql  # noqa: F401  (kept for callers)
    _pg = psycopg

#: Catch database failures with `except dbcompat.DBError` rather than naming
#: one driver's exception class - the driver in use depends on DATABASE_URL.
if IS_POSTGRES:
    DBError = (sqlite3.Error, psycopg.Error)
    OperationalError = (sqlite3.OperationalError, psycopg.OperationalError,
                        psycopg.errors.UndefinedTable, psycopg.errors.UndefinedColumn)
else:
    DBError = (sqlite3.Error,)
    OperationalError = (sqlite3.OperationalError,)


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

class Row(dict):
    """A result row that works like sqlite3.Row *and* like a dict.

    The existing code does both ``row["column"]`` and ``row[0]``, and passes
    rows to ``dict(row)``. All three keep working.
    """

    __slots__ = ("_seq",)

    def __init__(self, keys, values):
        super().__init__(zip(keys, values))
        self._seq = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._seq[key]
        if isinstance(key, slice):
            return self._seq[key]
        return super().__getitem__(key)


def _pg_row_factory(cursor):
    desc = cursor.description
    if desc is None:
        return lambda values: values
    keys = [c.name for c in desc]
    return lambda values: Row(keys, values)


# ---------------------------------------------------------------------------
# SQL translation
# ---------------------------------------------------------------------------

_RE_AUTOINC = re.compile(r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT", re.I)
_RE_INSERT_IGNORE = re.compile(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", re.I)
_RE_INSERT_REPLACE = re.compile(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\b", re.I)
_RE_NOCASE = re.compile(r"\bCOLLATE\s+NOCASE\b", re.I)
_RE_LIKE = re.compile(r"(?<!\bI)\bLIKE\b", re.I)
_RE_INSERT_TABLE = re.compile(r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", re.I)
_RE_RETURNING = re.compile(r"\bRETURNING\b", re.I)


def _split_placeholders(sql):
    """Replace ? with %s, but never inside a quoted string literal."""
    out = []
    in_single = False
    in_double = False
    for ch in sql:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
    return "".join(out)


def translate(sql):
    """Rewrite one SQLite statement into its Postgres equivalent."""
    if not IS_POSTGRES:
        return sql

    s = sql

    # Auto-incrementing integer primary keys.
    s = _RE_AUTOINC.sub("SERIAL PRIMARY KEY", s)

    # Upsert-ish inserts.
    if _RE_INSERT_IGNORE.search(s):
        s = _RE_INSERT_IGNORE.sub("INSERT INTO", s)
        if "ON CONFLICT" not in s.upper():
            s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    elif _RE_INSERT_REPLACE.search(s):
        # No safe generic rewrite; the codebase does not currently use it,
        # but fail loudly rather than silently changing behaviour.
        raise NotImplementedError(
            "INSERT OR REPLACE has no automatic Postgres translation. "
            "Write an explicit ON CONFLICT ... DO UPDATE instead."
        )

    # Case-insensitive comparison. SQLite's NOCASE becomes a non-deterministic
    # ICU collation created in ensure_postgres_prereqs().
    s = _RE_NOCASE.sub('COLLATE "{}"'.format(CI_COLLATION), s)

    # SQLite's LIKE is case-insensitive by default; Postgres's is not.
    # ILIKE preserves the behaviour every existing search relies on.
    s = _RE_LIKE.sub("ILIKE", s)

    # Placeholders last, so nothing above has to care about them.
    s = _split_placeholders(s)
    return s


# ---------------------------------------------------------------------------
# Connection / cursor wrappers
# ---------------------------------------------------------------------------

class _PGCursor:
    """Wraps a psycopg cursor so it behaves like a sqlite3 cursor."""

    def __init__(self, cur, conn):
        self._cur = cur
        self._conn = conn
        self._lastrowid = None

    # -- execution ----------------------------------------------------------

    def execute(self, sql, params=()):
        stmt = translate(sql)
        self._lastrowid = None

        table = None
        m = _RE_INSERT_TABLE.match(stmt)
        if m and not _RE_RETURNING.search(stmt):
            table = m.group(1)

        if table and self._conn.table_has_id(table):
            stmt = stmt.rstrip().rstrip(";") + " RETURNING id"
            self._cur.execute(stmt, tuple(params))
            row = self._cur.fetchone()
            if row is not None:
                self._lastrowid = row[0]
            return self

        self._cur.execute(stmt, tuple(params))
        return self

    def executemany(self, sql, seq_of_params):
        self._cur.executemany(translate(sql), [tuple(p) for p in seq_of_params])
        return self

    # -- results ------------------------------------------------------------

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def fetchmany(self, size=None):
        return self._cur.fetchmany(size) if size else self._cur.fetchmany()

    def __iter__(self):
        return iter(self._cur)

    @property
    def lastrowid(self):
        return self._lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description

    def close(self):
        self._cur.close()


class _PGConnection:
    """Wraps a psycopg connection so it behaves like a sqlite3 connection.

    The important difference this smooths over: sqlite3 lets you call
    ``conn.execute(...)`` directly and psycopg does not. db.py does that in
    ninety-odd places.
    """

    _id_tables = None  # cached: which tables have an "id" column

    def __init__(self, conn):
        self._conn = conn

    # -- sqlite3-style conveniences ----------------------------------------

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executescript(self, script):
        cur = self.cursor()
        for statement in script.split(";"):
            if statement.strip():
                cur.execute(statement)
        return cur

    def cursor(self):
        return _PGCursor(self._conn.cursor(row_factory=_pg_row_factory), self)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False

    # -- schema knowledge ---------------------------------------------------

    def table_has_id(self, table):
        """True when `table` has an "id" column, so INSERTs can RETURN it."""
        cls = type(self)
        if cls._id_tables is None:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND column_name = 'id'"
            )
            cls._id_tables = {r[0].lower() for r in cur.fetchall()}
            cur.close()
        return table.lower().strip('"') in cls._id_tables

    @classmethod
    def forget_schema(cls):
        """Call after DDL that creates tables, so the id-column cache reloads."""
        cls._id_tables = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def connect(sqlite_path):
    """Open a connection to whichever database is configured."""
    if IS_POSTGRES:
        raw = _pg.connect(DATABASE_URL, autocommit=False)
        return _PGConnection(raw)

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_postgres_prereqs(sqlite_path):
    """Create the case-insensitive collation NOCASE translates into.

    Safe to call repeatedly and a no-op on SQLite.
    """
    if not IS_POSTGRES:
        return
    conn = _pg.connect(DATABASE_URL, autocommit=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_collation WHERE collname = %s", (CI_COLLATION,))
        if cur.fetchone() is None:
            cur.execute(
                'CREATE COLLATION "{}" (provider = icu, '
                "locale = 'und-u-ks-level2', deterministic = false)".format(CI_COLLATION)
            )
        cur.close()
    finally:
        conn.close()


def table_columns(cur, table):
    """Column names of `table`, on either engine.

    Replaces the PRAGMA table_info() calls, which are SQLite-only.
    """
    if IS_POSTGRES:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s",
            (table.lower().strip('"'),),
        )
        return {r[0] for r in cur.fetchall()}
    rows = cur.execute("PRAGMA table_info({})".format(table)).fetchall()
    return {r["name"] for r in rows}


def schema_changed():
    """Tell the layer that new tables may exist."""
    if IS_POSTGRES:
        _PGConnection.forget_schema()


def engine_name():
    return "postgres" if IS_POSTGRES else "sqlite"


def describe():
    """One line for logs and the settings screen."""
    if not IS_POSTGRES:
        return "SQLite (single file)"
    # Never leak the password into a log line.
    safe = re.sub(r"//[^@/]*@", "//***@", DATABASE_URL)
    return "PostgreSQL ({})".format(safe)
