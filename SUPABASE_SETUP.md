# Sign-in setup (Supabase)

DHARANI 360 now signs people in with their **work email**, checked against
**Supabase Auth**. Only five addresses are permitted:

| Email | DHARANI 360 account | Role |
|---|---|---|
| akbar@dharanis.ae | akbar | Director |
| ramya@dharanis.ae | ramya | Director |
| khalidaamyn@dharanis.ae | khalidaamyn | Admin / Operations |
| baqeer@dharanis.ae | baqeer | Agent |
| greetus@dharanis.ae | greetus | Admin / Operations |

Every other account — including the old `admin` login — is deactivated.

---

## How it fits together

Supabase answers exactly one question: *is this really them?* It checks the
email and password and nothing else.

Everything after that stays local. Which role someone holds, which departments
they can open, whose name goes on a record — all of that continues to come
from the `users` table in `instance/dharani360.db`, because that is what the
rest of the system already reads.

Three things must all be true for someone to get in:

1. the address is on the list in `supabase_auth.py` (`ALLOWED_EMAILS`),
2. Supabase accepts the password,
3. an **active** local account exists with that email.

Any one failing is a refusal, with the same wording every time so a wrong
guess cannot be used to work out which addresses exist. A stray user created
in the Supabase dashboard therefore cannot, by itself, get into this system.

---

## One-time setup

### 1. Get the two public values

In your Supabase dashboard for the **dharani360** project:
**Project Settings → API**. Copy:

- **Project URL** — looks like `https://abcdefgh.supabase.co`
- **anon / publishable key** — the long `eyJ...` string labelled *anon public*

### 2. Write them into the config

Copy `supabase_config.example.json` to `supabase_config.json` and fill in
those two values:

```json
{
  "url": "https://abcdefgh.supabase.co",
  "anon_key": "eyJhbGciOi...",
  "offline_fallback": true
}
```

`supabase_config.json` is in `.gitignore` and is never shared. **Only the anon
key belongs in it.** The anon key is designed to be public — it is safe on
this machine.

### 3. Create the five accounts

```
setup_signin.bat
```

It will ask for the **service_role key** (same dashboard page). That key can
read and write anything in the project, so:

- it is used for the few seconds the script runs and **never written to disk**,
- do not put it in `supabase_config.json`, do not email it,
- if it ever leaks, rotate it under **Project Settings → API**.

The script creates the five users in Supabase (already email-confirmed, so
nobody has to click a link), attaches each address to its existing local
account, and deactivates everything else.

**Prefer not to handle that key?** Create the five users by hand in the
dashboard — **Authentication → Users → Add user**, tick *Auto Confirm User* —
then run `setup_signin.bat --local-only` to do just the local half.

### 4. Start the app

```
start.bat
```

The sign-in screen shows a small status line: green *Secured by Supabase* when
the project is reachable.

---

## Before you finish setup

Until `supabase_config.json` exists, the five addresses still sign in using the
password stored locally, and the screen says so: *Supabase sign-in not
configured yet*. That is deliberate — an update should never leave the office
unable to open the system. Nothing else changes: the allowlist and the
deactivated accounts are already enforced.

Once the config is in place, Supabase becomes the thing that actually checks
the password.

---

## What happens when the internet is down

This system runs on one office machine that is not always online, and an
authentication service that cannot be reached would otherwise mean nobody can
open the system at all.

So: a successful Supabase sign-in refreshes a local copy of the password hash,
and that copy is accepted **only while Supabase itself is unreachable**. The
sign-in screen says *Supabase unreachable — offline sign-in only*, and the
person sees a warning after signing in.

To require Supabase every single time, set `"offline_fallback": false` in
`supabase_config.json`. Be aware that this means an internet outage locks
everyone out of the system.

---

## Changing who can sign in

Adding or removing a person takes two steps — deliberately, so a Supabase
account alone is never enough:

1. Edit `ALLOWED_EMAILS` in `supabase_auth.py`.
2. Create the user in Supabase, and make sure a local account with that email
   exists and is active (Users & Access, or add it to `ACCOUNTS` in
   `setup_signin.py` and re-run).

To remove someone, take them out of `ALLOWED_EMAILS` **and** deactivate them in
Users & Access. Deleting their Supabase user is also worth doing, but the
allowlist is what actually stops them.

---

## If you are locked out

`admin` is deactivated, so there is no back door by design. To recover, open
`instance/dharani360.db` with any SQLite tool and run:

```sql
UPDATE users SET active = 1 WHERE username = 'admin';
```

then sign in with the address you re-enable. Keep a backup of that file.

---

## A note on the passwords

The five passwords were set as supplied. They follow a predictable
`Name@2024` pattern and were shared in a chat message, so they should be
treated as known to more people than intended.

Each person can change their own under **Change Password**, and doing so
updates the local copy — but note it does **not** change the password held in
Supabase, which is the one actually checked when you are online. To change a
password properly, do it in the Supabase dashboard (**Authentication → Users →
… → Reset password**), or ask for a self-service reset flow to be added.
