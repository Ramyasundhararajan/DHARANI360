# DHARANI 360 — running it

The things you will need to do, and the order to do them in. Written to be
followed by someone who is not the person who built it — including you, six
months from now, at nine in the evening.

---

## Every day (automatic)

| What | How it runs | If it stops |
|---|---|---|
| Backup | `backup.bat` from Task Scheduler | See **Backups** below |
| Compliance digest | `send_digest.bat` from Task Scheduler | Check SMTP settings on the Settings page |
| Uptime check | Your monitor pings `/healthz` | See **When it is down** |

---

## Checking the system is healthy

**`python config.py`** — prints every setting, where it came from, and warns
about combinations that cause damage. Run it after any change to `.env`, and
before every deploy.

**`python smoketest.py`** — 50 checks: sign-in, CSRF refusal, lockout, health,
every page, all 112 registers and blank forms, a create/edit/delete cycle, and
the audit entries that resulted. Takes a couple of minutes. If this passes, the
system works.

**`GET /healthz`** — answers in JSON without a sign-in:

```json
{"status": "ok", "checks": {"database": "ok", "storage": "ok"}}
```

`200` means healthy, `503` means degraded. Point a free uptime monitor at it
(UptimeRobot, Healthchecks.io, Better Stack) and you will hear about an outage
before a client does. It reveals nothing about the system, so it is safe to
leave public.

---

## When something breaks

The person sees a short reference code, e.g. *"Quote reference A7F3C2"*.

```
findstr A7F3C2 instance\logs\errors.log     (Windows)
grep    A7F3C2 instance/logs/errors.log     (Mac/Linux)
```

That gives you the full traceback, the URL, the signed-in user and their IP.
Logs rotate at 2 MB and keep five files, so they cannot fill the disk.

## When it is down

1. `GET /healthz` — is it the app or the database?
2. `"database": "unreachable"` → the database server is down or the connection
   string is wrong. Check `python config.py`.
3. `"storage": "not writable"` → the disk is full, or permissions changed.
4. Neither answers at all → the web process is not running. Restart it.
5. Still stuck → restore the most recent backup onto a working machine and run
   from there. That is what the backups are for.

---

## Backups

```
python backup.py create --to "C:\Users\ramya\OneDrive\Dharani360 Backups"
python backup.py list
python backup.py verify <file>        prove it is readable BEFORE you need it
python backup.py restore <file>       put it back (takes a safety copy first)
```

Set `COPY_TO` in `.env` and the off-site copy happens on every run without the
flag. **A backup on the same disk as the database is not a backup** — the two
are lost together. `config.py` warns you when `COPY_TO` is unset.

**Automate it (Windows):** Task Scheduler → Create Basic Task → Daily → Start a
program → `backup.bat` in this folder.

**Automate it (Mac/Linux):** `0 2 * * * cd /path/to/portal && python backup.py create`

**Run `verify` at least once, and once a quarter after that.** A backup nobody
has restored is a guess.

---

## Sign-in problems

**"Too many failed sign-in attempts."** Eight failures inside fifteen minutes
locks that address out, for both wrong *and* right passwords. It clears itself
after fifteen minutes. To clear it immediately:

```
python -c "import db; db.clear_login_failures('someone@example.com')"
```

Every failure and lockout is in **Audit Trail** under `login.failed` and
`login.blocked` — check there before assuming someone forgot their password.
A run of failures against several addresses is somebody probing you.

**Somebody forgot their password.** They can use **Forgot your password?**
on the sign-in page themselves — a one-time link, good for 30 minutes. That
needs SMTP configured. Check the Audit Trail for `reset.requested` and
`reset.completed`; `reset.failed` means the email could not be sent, and the
link is written to `instance/logs/errors.log` so you can pass it on manually.

**Somebody is locked out and needs in now.** Users & Access → their row →
Reset Password. A one-time password appears once on screen; share it securely,
and they must set their own at next sign-in.

---

## Changing the schema

```
python migrations.py status     what is applied, pending, and orphaned
python migrations.py check      non-zero means the schema would change
python migrations.py upgrade    apply it
```

**Back up first.** `upgrade` says so too.

Nothing is ever dropped. A field removed from `forms_data.py` leaves its
column and its records in place, reported as an orphan by `status`. If you
truly want a column gone, do it by hand, deliberately, after a backup.

## Moving attachments to object storage

```
python migrate_files.py check
python migrate_files.py upload
python migrate_files.py verify
```

Local copies are never deleted. Keep `instance/uploads/` until `verify` is
clean **and** you have one verified backup after that. Then remove it
yourself.

## Changing settings

Everything lives in `.env` (never committed). `.env.example` documents every
setting. After any change:

```
python config.py        confirm it reads what you intended
python smoketest.py     confirm nothing broke
```

Restart the app for changes to take effect.

**Rotating a secret** (a key was shared, or someone left):

1. New `SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Put it in `.env`, restart. Everyone is signed out and must sign in again —
   that is the point.
3. Supabase keys rotate in the Supabase dashboard; update `SUPABASE_ANON_KEY`.
4. Never put a `service_role` key in `.env`. `config.py` refuses to stay quiet
   about it if you do.

---

## Adding someone

Users & Access → Add User. Give them a role, not the admin account. Their work
email must also be on the allowlist — `ALLOWED_EMAILS` in `.env`, or the list
in `supabase_auth.py` if that is unset.

**Removing someone:** set them inactive rather than deleting. Their records,
their sign-in history and their audit entries are kept either way — a
compliance system must not lose who did what because somebody left.

---

## Deploying a change

1. `python smoketest.py` locally — 50 checks, both databases if you can.
2. `git push`. GitHub Actions runs the same checks on SQLite **and**
   PostgreSQL, plus a backup create/verify. A red run means do not deploy.
3. Take a backup before deploying anything that touches the database.
4. Deploy. Then `GET /healthz` and open one real record.

---

## What is deliberately not automatic

- **Restores.** Always a human decision — `restore` asks you to type the word.
- **Deleting records.** Deletion is logged, never silent, and the audit entry
  keeps a copy of what was removed.
- **Preview data.** `preview.bat` uses its own database and cannot reach a
  live one, so it is safe to run at any time.
