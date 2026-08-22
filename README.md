# DHARANI 360
### Real Estate Operations, Compliance & Growth System
People · Process · Property · Protection · Performance

A working portal, not a slide deck: 112 forms across 17 departments, each
feeding a permanent register (a real database table), a real login system
with role-based access, records that automatically cross-link to each
other, file attachments, and an Admin Control Tower dashboard that watches
every expiry date across the company.

> "The form is merely the input. The register is the memory of the company."

---

## 1. How to start it

**Windows** — double-click `start.bat`. First run takes a minute (it sets
up a small, private copy of Flask). Your browser opens automatically to
`http://127.0.0.1:5000`. To stop, close the black terminal window. Run
`start.bat` again anytime to bring it back up — instant after the first time.

**Mac / Linux** — `./start.sh` in this folder (first time: `chmod +x start.sh && ./start.sh`).

**Requirement:** Python 3.9+. If `start.bat` says Python wasn't found,
install it from python.org (tick "Add python.exe to PATH") and try again.

## 1b. Seeing it without risking anything

**Windows** — double-click `preview.bat`. **Mac / Linux** — `./preview.sh`.

Your browser opens on a fully working DHARANI 360, already signed in, filled
with a sample brokerage: licences expiring inside 30 days, leads, viewings,
transactions and a compliance calendar that opens red rather than empty.

It cannot touch your real records:

- it uses its own database in `instance/preview/`, never `instance/dharani360.db`
- it ignores `DATABASE_URL` completely, so it cannot reach a live server
- it only listens on this computer; the automatic sign-in works for nothing else
- every page carries an orange **PREVIEW** banner, so a screenshot of sample
  data can never be mistaken for the company's real register

Use it to check a change before trusting it, and to demo the system to a
client without showing them anybody's real data. `preview.bat --fresh` throws
the sample data away and builds it again.

## 2. Signing in

The first time you open the portal you'll land on a login screen. Default
administrator account:

- **Username:** `admin`
- **Password:** `dharani360`

You'll be forced to set your own password immediately after the first
login — do that, then create real named accounts for everyone else from
**Users & Access** (see section 4) rather than sharing this one login.

## 3. Where your data lives

Everything is saved permanently in one file:

```
instance/dharani360.db
```

Uploaded attachments (scanned passports, licences, contracts...) live
under `instance/uploads/`. Both **are** your company's data — back them
up the way you'd back up an important spreadsheet (copy to OneDrive/USB on
a schedule). Nothing is sent anywhere else; the system runs entirely on
this computer and is only reachable from this computer (`127.0.0.1` =
localhost). To move the whole system to another PC, copy this entire
folder, `instance/` included.

## 4. Roles & access (Users & Access page, Director only)

Every account has exactly one role, and a role can only see its assigned
departments — this is the "receptionist / agent / accountant / director"
access-level model from the original design brief, enforced in code, not
just written down:

| Role | Sees |
|---|---|
| Director / Owner | Everything, plus Users & Settings |
| Operations Manager | Everything (not Users & Settings) |
| Sales Manager | Agents, Sales/Leads/Clients, Properties, Transactions |
| Agent | Agents, Sales/Leads/Clients, Properties |
| Receptionist | Sales, Leads & Clients only |
| Accountant | Finance, Corporate & Licensing, Vendors, Compliance |
| Admin / Operations | HR, Assets/IT, Vendors, Corporate & Licensing, Compliance |

A department a user can't access is hidden from their dashboard and
department cards, greyed out (with a lock icon) in the sidebar, and
directly blocked (403) if they try the URL. To add a role or change what
it can see, edit `access.py` — one dictionary, nothing else to touch.

From **Users & Access**, a Director can create accounts, change a user's
name/role/active status, and issue a one-time password reset (shown once
on screen — share it securely and the user is forced to set their own
password at next login).

## 5. The Admin Control Tower (Dashboard) & department dashboards

The home page is the single screen your administrator should open every
morning — computed live from real data:

- **Total records**, scoped to what your role can see
- **🔴 Urgent** — anything with an expiry/due date within 30 days, or
  already overdue
- **🟠 Upcoming** — due within 31–90 days
- One card per accessible department, with its own red/amber counts
- **Recent Activity** — last 15 things entered anywhere you have access

Click into any department and you get the same treatment scoped to that
department alone: its own stats, its own red/amber list, all its forms
with live record counts, and its own recent-activity feed.

Each department also gets its own purpose-built panels (computed live in
`insights.py`, not decorative) reflecting how that part of the business
actually works:

- **Corporate & Licensing** — licence validity, the compliance calendar
  due in the next 30 days, and a breakdown of licences/permits on file.
- **People & HR** — headcount, an Employee Lifecycle funnel (Onboarding →
  Active → On Leave → Exit in Progress → Exited), leave requests awaiting
  approval, and open discipline/grievance items.
- **Agents & Brokers** — active-agent count, lead-ownership disputes,
  and a deals-closed leaderboard from the latest performance reviews.
- **Sales, Leads & Clients** — a Sales Pipeline funnel (Leads → Qualified
  → Viewings → Offers → Converted), follow-ups due within 7 days, and
  lead-source mix.
- **Properties & Owners** — portfolio-by-status breakdown and owner
  authorizations expiring within 90 days.
- **Transactions & Commissions** — a Transaction Pipeline funnel (Opened →
  Docs Complete → Commission Calculated → Approved/Paid → Closed) and the
  commission approval queue.
- **Finance & Accounting** — a merged approval queue across expense
  claims and payments, plus the running petty-cash balance.
- **AML, KYC & Compliance** — an AML risk-rating distribution (colour-coded
  Low/Medium/High) and open escalations/incidents.
- **Assets, IT & Security** — the asset register by type and open
  security incidents.
- **Vendors & Administration** — vendor contracts by status and
  due-diligence checks pending.

These panels are driven entirely by the same registers everything else
uses — as soon as a form is submitted, the relevant department dashboard
reflects it. With zero records yet, every panel just shows a clean empty
state rather than an error.

## 6. Every record links to related records automatically

Open any record and you'll see a **Related Records** panel below it. If a
transaction, a lead, and a client registration all mention the same
client name, or a property appears in both Property Onboarding and a
Transaction, they show up linked to each other automatically — no manual
cross-referencing required. This works off shared field names (lead ID,
client name, agent name, property reference, transaction reference,
employee name, vendor name, asset reference, owner name, referral source)
defined once in `forms_data.py` as `LINK_FIELD_NAMES` — add that field
name to a new form and it links up with everything else automatically.

Note the honest limit: linking is by matching text value in a same-named
field, not a real foreign key. Two different "Michael Chen"s would show
as related to each other. For the reference fields this is built around
(IDs, ref numbers, transaction numbers) that's rarely an issue; for common
names, sanity-check what you see.

## 7. File attachments

Every record has an **Attachments** section — attach the actual scanned
passport, trade licence, signed contract, etc. Allowed types: PDF, Word,
Excel, images, text/CSV, up to 15MB each. Files are stored under
`instance/uploads/<form>/<record id>/` and listed with uploader name and
date; download or remove them from the record's page.

## 8. Compliance Calendar & Search Everything

**Compliance Calendar** merges every date-tracked item across every
department you can access — licences, broker cards, POAs, owner
authorizations, marketing authorizations, vendor contracts, asset
warranties — into one sorted, color-coded list (filter 30/90/180 days or
see everything). **Search Everything** searches every text field in every
register you can access at once.

## 9. Registers: sorting, filtering, pagination, CSV export

Click any column header in a register to sort by it (click again to
reverse). Long registers page 25 rows at a time. The filter box searches
every text field in that register. **Export CSV** always exports the full
register, ignoring the current filter/page, for anyone who wants to open
it in Excel.

## 10. Automated compliance email reminders

Once you configure SMTP on the **Settings & Email Digest** page (Director
only — host, port, username/app-password, from/to addresses), DHARANI 360
can send a daily red/amber digest by email, without the portal needing to
be open. Use **Send Test Digest Now** on that page to confirm it works
before automating it.

To automate it on Windows:

1. Open **Task Scheduler** → **Create Basic Task**.
2. Name it "DHARANI 360 Digest", trigger **Daily** at your preferred time.
3. Action: **Start a program** → Browse to `send_digest.bat` inside this folder.
4. Finish. It will now run once a day even if the portal isn't open, and
   silently does nothing if there's genuinely nothing red or amber.

You can also run `python email_digest.py` (or `python email_digest.py
--force` to send even when everything's green) any time to test manually.

## 11. Print-friendly records

Open any record and click **Print** — it renders a clean, sidebar-free
printout of that record's details for a physical file.

## 12. Adding your own forms/registers later

Everything the portal knows about — every department, every form, every
field, which fields link across registers — is defined in one place:
`forms_data.py`. To add another form, add one entry to the `FORMS` list there
(copy an existing one as a template) and restart the app; the database
table, the entry form (with automatic section grouping), the register
table, sorting, CSV export, attachments, related-record linking and (if
you give it an `expiry_field`) the compliance calendar are all created
automatically. No other file needs to change.

## 13. Running it as shared software

Everything above works on one PC with no setup. These three switches turn
the same code into something a whole office can use at once.

### A real database

Set one environment variable and DHARANI 360 talks to PostgreSQL instead of
the local file. Nothing else changes — the same registers, the same screens.

```
DATABASE_URL=postgresql://user:password@host:5432/dharani360
```

Leave it unset and it stays on SQLite exactly as before. With Postgres you
can also run more than one web worker (`GUNICORN_WORKERS=4`), which is what
lets several people write at the same time without waiting for each other.
`dbcompat.py` handles the differences; no query in `db.py` had to be
rewritten for one engine or the other.

### The audit trail

Every change to every register is now recorded: who changed which field,
what it was before, what it became, when, and from which address. Records
are written automatically and the application never edits or deletes them.

- **Audit Trail** in the sidebar (Director only) shows everything, filterable
  by person, action, or any value.
- Every record page has a **History** panel showing that record's own changes.
- Account changes are logged too — roles granted, accounts created or
  removed, passwords reset. The password itself is never written down.

This is the difference between a system that holds your records and a system
that can prove what happened to them.

### Backups you have actually tested

```
python backup.py create             make a backup now
python backup.py list               see what you have
python backup.py verify <file>      prove a backup is readable and complete
python backup.py restore <file>     put it back (takes a safety copy first)
```

`backup.bat` does the same by double-click, and Windows Task Scheduler can
run it daily (Create Basic Task → Daily → Start a program → `backup.bat`).
A backup holds the database plus every attachment, staff photo, chat file and
library file. It deliberately excludes the signing key, which is a credential
rather than data.

**Run `verify` at least once.** A backup nobody has restored is not a backup.

### Knowing it is alive, and why it broke

`GET /healthz` answers `{"status": "ok"}` without a sign-in, and reports
whether the database and disk are actually reachable. Point a free uptime
monitor at it and you hear about an outage before a client does.

When a page fails, the person sees a short reference code and the full
traceback goes to `instance/logs/errors.log` with the URL, the user and that
same code. "It broke" becomes "show me reference A7F3C2".

See **OPERATIONS.md** for the whole runbook.

### Security when it leaves the desk

- Every form is protected against cross-site request forgery, so another
  website cannot make your browser submit something here using your session.
- Session cookies are HttpOnly and SameSite, and marked Secure automatically
  when the site is hosted. Force it either way with `SECURE_COOKIES=1` or `0`.
- Sign-ins expire after 12 hours of inactivity (`SESSION_HOURS` to change).
- Eight failed sign-ins for one address inside fifteen minutes locks it out,
  right password included. Every failure and lockout is in the Audit Trail,
  so a run of them against several addresses is visible as what it is.

Check the whole thing still works after any change:

```
python smoketest.py
```

It signs in, opens every page, every register and every blank form, runs a
create/edit/delete cycle, and confirms the audit trail recorded it — 50
checks, on whichever database is configured.

## 14. Honest limits of this version (read this)

- **Not yet multi-tenant.** One installation serves one company. Running it
  for several brokerages means several deployments today.
- **Roles are defined in code.** `access.py` is one dictionary; changing what
  a role can see means editing it and restarting, not a settings screen.
- **Cross-record linking is name/value matching, not a relational
  database.** See section 6.
- **Login is not penetration-tested.** The protections in section 13 close
  the obvious doors. They are not a substitute for a security review before
  the system holds another company's data.
- **Email digest requires you to supply your own SMTP account** (Gmail,
  Outlook/365, Zoho, etc. all work with an app password). DHARANI 360
  can't send email on your behalf without those credentials.
- **This is not legal, tax or immigration advice.** None of the pre-filled
  status options, roles, or field labels should be read as a definitive
  statement of UAE law (leave entitlements, gratuity, VAT/Corporate Tax
  thresholds, AML retention periods, etc.) — confirm with your
  accountant/lawyer and adjust `forms_data.py` if needed.

## 15. What's inside this folder

```
dharani360-portal/
  app.py             <- routes/logic
  db.py              <- database engine (generic, driven by forms_data.py)
  dbcompat.py        <- lets the same code run on SQLite or PostgreSQL
  security.py        <- CSRF protection, session and header hardening
  backup.py          <- backup, verify and restore
  smoketest.py       <- 50 checks that the whole system still works
  observability.py   <- /healthz health check and error logging
  OPERATIONS.md      <- how to run it: backups, outages, secrets, deploys
  config.py          <- every setting, and where it came from
  preview.py         <- sample-data preview, isolated from real records
  forms_data.py      <- master library: 17 departments, 112 forms/fields, linking rules
  access.py          <- roles & which departments each role can see
  auth.py            <- login/session/password handling
  email_digest.py    <- standalone compliance-digest emailer
  send_digest.bat    <- launcher for Windows Task Scheduler
  requirements.txt   <- the one dependency (Flask)
  start.bat / start.sh
  templates/         <- page templates
  static/style.css   <- styling
  instance/          <- created on first run: dharani360.db + uploads/
```
