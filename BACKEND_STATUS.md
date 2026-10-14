# Backend status — 21 Sep 2026

The portal has been moved off "local SQLite only" and onto a real backend.
Everything below is done except the two lines marked TODO, which need a
password only you should type.

## What is already set up

**Supabase project `dharani360-prod`** — region ap-south-1 (Mumbai, closest
to Dubai), inside the same organisation as the `crm` project. Supabase bills
per organisation, so whatever plan that org is on covers this project too.

**Storage bucket `dharani360-files`** — private, 15MB per-file cap, matching
the limit the portal already enforces on attachments.

**`.env`** — written and gitignored. Holds the project URL, the anon key, the
bucket, the S3 endpoint, `DEMO_MODE=0`, and a freshly generated 64-character
`SECRET_KEY`.

**`supabase_config.json`** — repointed at the new project. The previous file
pointed at `bhmhswcpjfjxekagcdlh.supabase.co`, which no longer exists in the
account; that is why the sign-in page kept saying Supabase was unreachable.
The old file is kept as `supabase_config.json.bak-20260921`.

## Proven, not assumed

The portal's own smoke test was run against a real PostgreSQL 16 server, not
just SQLite:

    all 50 checks passed on postgres

Same 50 that pass on SQLite. Every one of the 112 forms opens, every register
opens, the create/edit/delete cycle works, and the audit trail records the
before and after values of each changed field. Switching the database over is
a settings change, not a rewrite.

## TODO — two lines, both in `.env`

1. `DATABASE_URL=`
   Supabase dashboard -> Project Settings -> Database -> Connection string ->
   **Transaction pooler** (port 6543). Paste it whole, replacing
   `[YOUR-PASSWORD]` with the database password.

2. `S3_ACCESS_KEY=` and `S3_SECRET_KEY=`
   Project Settings -> Storage -> S3 access keys -> New key.

Then start the portal normally. It creates all 128 tables on first connect —
112 form registers plus users, audit_log, attachments, chat, calls, todos,
notes, meetings, holidays, settings and the rest. Nothing to run by hand.

## Then, and this matters

Once the tables exist, row-level security must be switched on for all of
them. Supabase exposes every public table over its REST API to anyone holding
the anon key, and that key travels in `.env` and in any hosting environment
variables. The portal connects straight to Postgres and is unaffected by RLS,
so turning it on closes the REST hole and changes nothing else.

Until that is done, do not put real client records in.

## Sign-in accounts

Authentication -> Users -> Add user, for the five addresses already hard-coded
as the allow-list in `supabase_auth.py`:

    ramya@dharanis.ae, akbar@dharanis.ae, khalidaamyn@dharanis.ae,
    baqeer@dharanis.ae, greetus@dharanis.ae

Tick "Auto Confirm User" or they cannot sign in. Any other address is refused
before the password is even checked.

## Hosting — still open

The database decision above is independent of where the Flask app runs. With
records living in Supabase the app server holds nothing and is disposable,
so this can be decided later without redoing any of the above.
