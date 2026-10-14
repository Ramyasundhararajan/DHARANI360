# DHARANI 360 — n8n automation flows

Eleven workflows, generated against this installation's own `forms_data.py`
(112 forms, 17 departments), so every table name, column name and document
number format in them is the real one. Every SQL statement in every flow has
been executed against a Postgres database built by the portal's own
`db.init_db()`, and every Code node has been unit-tested.

They implement the Phase 1 items from `AUTOMATION_MAP.html`.

| File | Automation map | What it does |
|---|---|---|
| `00-notification-dispatcher.json` | A-03 | One place that knows how to reach a person — email, WhatsApp, Slack. Every other flow calls it. |
| `01-expiry-reminder-ladder.json` | B-02, B-03, B-04 | Chases the **named owner** of every expiring document at 90/60/30/14/7/3/1 days, then daily. Opens a renewal to-do at 90 and 30. |
| `02-lead-capture-dedupe.json` | D-01 | One webhook for Property Finder, Bayut, Dubizzle, Meta and the website. Deduplicates, writes into SAL-001 with a real `DR-` number. |
| `03-lead-assignment-sla.json` | D-02, D-03, D-06 | Assigns to the least-loaded agent, notifies them, then checks the response clock and reclaims the lead if nothing was logged. |
| `04-agent-morning-followups.json` | D-05 | 07:30: each agent gets their own overdue / today / this-week list. |
| `05-approvals-chaser.json` | J-02, H-01 | Sweeps 13 approval registers every 2 hours. Reminds at 24h, escalates at 72h, sends anything over the value threshold straight to the Director. |
| `06-employee-onboarding-chain.json` | G-01, G-07 | One new HR-002 record opens HR-003, HR-005, HR-006 and seven dated to-dos, with probation and appraisal diarised from the join date. |
| `07-commission-invoice-dunning.json` | F-03 | Chases unpaid commissions and vendor invoices at 7/30/60/90 days, then weekly, escalating the wording as it goes. |
| `08-weekly-management-pack.json` | K-02 | Monday 08:00: pipeline, compliance horizon, money waiting and a 30-day agent leaderboard, as one HTML email. |
| `09-anomaly-watch.json` | K-04 | Every 6 hours: failed sign-ins, deletion spikes, a growing overdue backlog, lead volume collapsing, leads left unassigned. Silent when all is well. |
| `10-rules-engine-event-router.json` | A-02 | "When this happens, do that" as an editable table of rules. Add a line, get a new automation. |

## Install order

1. **`00-notification-dispatcher.json` first.** Import it, open it, copy the
   workflow ID out of the browser address bar, and paste it into the *Notify*
   node of every other flow (they ship with the placeholder
   `DISPATCHER_WORKFLOW_ID`).
2. Import the rest. Each one has a sticky note at the top explaining itself.
3. In each flow, open the **Config** node and correct the addresses and the
   portal URL. Nothing else is hard-coded.
4. `02` also needs the workflow ID of `03` pasted into its *Assign It* node.

## Credentials to create in n8n

| Credential | Type | Used by |
|---|---|---|
| `Dharani 360 - Postgres` | Postgres | every scheduled flow |
| `Dharani 360 - SMTP` | SMTP | the dispatcher |
| `Dharani 360 - Slack` | Slack API | the dispatcher |
| `Dharani 360 - WhatsApp (Meta Graph)` | Header Auth | the dispatcher |

**Postgres** — the same connection string as `DATABASE_URL` in `.env`. From
Supabase: Project Settings → Database → Connection string → Transaction pooler
(port 6543). Give n8n its own database role if you can; it needs `SELECT` on
everything, and `INSERT`/`UPDATE` on `frm_sal_001`, `frm_hr_003`, `frm_hr_005`,
`frm_hr_006`, `todos` and `counters`.

**WhatsApp** — Header Auth, name `Authorization`, value
`Bearer <your Meta permanent access token>`. Put the phone-number ID into the
dispatcher's Config node. The message template must be approved in Meta
Business Manager first; the flows use one template with a single body
parameter, named in `wa_template`.

## The two flows that need the portal to talk back

`06` and `10` are event-driven — they need DHARANI 360 to tell n8n the moment
a record is created or changed. Two files do that:

```
n8n_hooks.py         the wire itself - never blocks a save, never raises
apply_n8n_hooks.py   patches db.py for you, idempotently, with a .bak
```

Copy both into the portal folder, next to `db.py`, then:

```
python apply_n8n_hooks.py            # shows what it would change
python apply_n8n_hooks.py --write    # makes the change, keeps db.py.bak
python apply_n8n_hooks.py --undo     # puts the original back
```

Add to `.env`:

```
N8N_BASE_URL=https://your-n8n-host
N8N_EVENT_TOKEN=<python -c "import secrets; print(secrets.token_urlsafe(32))">
```

Restart the portal, then:

```
python n8n_hooks.py     # sends one test event
python smoketest.py     # confirms the 50 checks still pass
```

With `N8N_BASE_URL` unset, the hook sends nothing and the portal behaves
exactly as it did before — so it is safe to install ahead of using it.

`n8n_hooks.py` redacts passport numbers, Emirates ID numbers, IBANs, salaries
and bank details before anything leaves the building, and redacts the whole
body of the payroll, source-of-funds, beneficial-ownership and
bank-change registers. Edit `REDACT_FORMS` and `REDACT_FIELDS` at the top of
the file to change that.

## After they are running

Turn off `send_digest.bat` in Windows Task Scheduler — flow `01` replaces it
and does considerably more. Keep `backup.bat` where it is.

## Honest limits

- The flows read and write the registers directly over SQL. They do not go
  through `db.py`, so **changes they make are not written to the portal's audit
  trail**. Where a flow changes a record it stamps the record's own `notes`
  field instead, so the change is at least visible on the record. If audit
  coverage matters more than simplicity, replace those Postgres nodes with
  HTTP calls to a small API added to `app.py`.
- Flow `03` uses n8n's Wait node for the response clock. On n8n's free cloud
  tier a waiting execution counts against your quota; self-hosted it costs
  nothing.
- Dedupe in flow `02` matches on the last 9 digits of the phone. Two people
  sharing a phone would be treated as one lead — rare, and the alternative
  (matching nothing) is worse.
- `10` holds its rules in a Code node rather than a database table. That is
  deliberate: it is one place to edit, versioned with the workflow, and it does
  not need a settings screen built first. A rules *table* is A-02 proper, and
  wants the portal to own it.
