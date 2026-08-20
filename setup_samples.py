# -*- coding: utf-8 -*-
"""
DHARANI 360 - sample data for Chat and the Call Log
======================================================
Adds a handful of realistic internal chat messages between the team, and a set
of client call records, so the Chat and Calls screens have something in them
while you are learning the system.

Run it once:   double-click setup_samples.bat
           or: python setup_samples.py

Run setup_team.py FIRST - the chat messages are addressed to those accounts.

Safe to run more than once: it checks first and will not add a second copy.
Everything it adds is ordinary data, so you can delete any of it from the
screens themselves once you have real activity.
"""
import sys
from datetime import datetime, timedelta

import db

MARKER = "[sample]"


def _stamp(days_ago, hh, mm):
    d = (datetime.now() - timedelta(days=days_ago)).replace(
        hour=hh, minute=mm, second=0, microsecond=0)
    return d.isoformat(timespec="seconds")


# (from, to, message, days_ago, hour, minute)
CHATS = [
    ("akbar", "ramya", "Morning Ramya - can you check the trade licence renewal date? I think it is close.", 1, 8, 40),
    ("ramya", "akbar", "Checked. Licence expires 14 March, so the calendar will flag it at 90 days. Nothing due yet.", 1, 8, 52),
    ("akbar", "ramya", "Good. Please put the RERA broker cards on the same calendar.", 1, 8, 55),
    ("ramya", "akbar", "Done - both cards are in the register with expiry dates, so they will raise automatically.", 1, 9, 10),

    ("khalidaamyn", "ramya", "The new printer invoice came in. Which folder should it go in?", 1, 11, 15),
    ("ramya", "khalidaamyn", "File Manager, Finance folder. Add the vendor name in the description so it is searchable.", 1, 11, 22),
    ("khalidaamyn", "ramya", "Uploaded. Thanks.", 1, 11, 31),

    ("baqeer", "khalidaamyn", "Client viewing tomorrow at 4pm for Marina Tower 1204. Can you book the meeting room?", 0, 10, 5),
    ("khalidaamyn", "baqeer", "Booked. I have added it to the calendar so everyone can see it.", 0, 10, 12),
    ("baqeer", "khalidaamyn", "Perfect. I will log the call notes after.", 0, 10, 14),

    ("greetus", "akbar", "Draft announcement about the new hybrid policy is ready for your approval.", 0, 12, 30),
    ("akbar", "greetus", "Read it - approved. Publish it as one article, do not create a second version.", 0, 12, 48),
    ("greetus", "akbar", "Understood, updating the existing one and date-stamping it.", 0, 12, 52),

    ("ramya", "baqeer", "Reminder: log every client call, even the missed ones. It builds the client history.", 0, 14, 20),
    ("baqeer", "ramya", "Will do - logging today's now.", 0, 14, 26),
]

# Client call records for the Call Log register (DR-SAL-009)
CALLS = [
    dict(call_direction="Incoming", call_type="Video Call", contact_name="Ahmed Al Mansoori",
         contact_number="+971 50 100 0002", call_time="14:30", duration_minutes="24",
         related_lead="Marina Tower 1204", property_ref="PRO-0044", agent_name="Baqeer Muhammed",
         outcome="Viewing Booked", status="Follow-up Needed", days_ago=0, follow_up_in=1,
         summary="Discussed the 2BR marina view unit. Wants a viewing Tuesday afternoon."),
    dict(call_direction="Outgoing", call_type="Voice Call", contact_name="Fatima Hassan",
         contact_number="+971 50 100 0003", call_time="11:05", duration_minutes="7",
         related_lead="Business Bay studio", agent_name="Baqeer Muhammed",
         outcome="Call Back Later", status="Follow-up Needed", days_ago=1, follow_up_in=2,
         summary="Left a message about the Business Bay listing. Asked me to call back Thursday."),
    dict(call_direction="Missed", call_type="Voice Call", contact_name="Rashid Property Co",
         contact_number="+971 4 555 0100", agent_name="Khalida Amyn",
         outcome="No Answer", status="Follow-up Needed", days_ago=1, follow_up_in=0,
         summary="Missed while the office was closed. Needs a call back."),
    dict(call_direction="Incoming", call_type="Voice Call", contact_name="Ahmed Al Mansoori",
         contact_number="+971 50 100 0002", call_time="09:15", duration_minutes="5",
         agent_name="Baqeer Muhammed", outcome="Interested", status="Closed", days_ago=7,
         summary="First enquiry from the portal listing."),
    dict(call_direction="Outgoing", call_type="Video Call", contact_name="Priya Nair",
         contact_number="+971 55 200 0044", call_time="16:00", duration_minutes="18",
         related_lead="JVC townhouse", agent_name="Baqeer Muhammed",
         outcome="Offer Discussed", status="Follow-up Needed", days_ago=2, follow_up_in=1,
         summary="Walked through the JVC townhouse on video. Discussed an offer 4% under asking."),
    dict(call_direction="Incoming", call_type="Voice Call", contact_name="Sunil Menon",
         contact_number="+971 52 330 0091", call_time="13:40", duration_minutes="3",
         agent_name="Khalida Amyn", outcome="Wrong Number", status="Closed", days_ago=3,
         summary="Wrong number - looking for a different agency."),
    dict(call_direction="Outgoing", call_type="Voice Call", contact_name="Fatima Hassan",
         contact_number="+971 50 100 0003", call_time="10:20", duration_minutes="12",
         agent_name="Baqeer Muhammed", outcome="Viewing Booked", status="Closed", days_ago=5,
         summary="Booked a viewing for the Downtown 1BR."),
    dict(call_direction="Missed", call_type="Video Call", contact_name="Ahmed Al Mansoori",
         contact_number="+971 50 100 0002", agent_name="Baqeer Muhammed",
         outcome="No Answer", status="Closed", days_ago=4,
         summary="Missed video call - returned by voice the same afternoon."),
]


def main():
    db.init_db()

    known = {u["username"] for u in db.list_users()}
    missing = {u for c in CHATS for u in (c[0], c[1])} - known
    if missing:
        print("\n  These accounts do not exist yet: {}".format(", ".join(sorted(missing))))
        print("  Run setup_team.bat first, then run this again.\n")
        return

    # --- chat ---------------------------------------------------------------
    conn = db.get_conn()
    already = conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
    chats_added = 0
    if already:
        print("\n  Chat already has {} message(s) - leaving it alone.".format(already))
    else:
        for frm, to, body, days, hh, mm in CHATS:
            conn.execute(
                "INSERT INTO chat_messages (from_user, to_user, body, created_at, read_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (frm, to, body, _stamp(days, hh, mm), None)
            )
            chats_added += 1
        conn.commit()
    conn.close()

    # --- call log -----------------------------------------------------------
    existing_calls, _ = db.get_records("SAL-009")
    marked = [r for r in existing_calls if MARKER in (r.get("notes") or "")]
    calls_added = 0
    if marked:
        print("  Sample calls are already loaded ({} of them) - leaving them alone.".format(len(marked)))
    else:
        today = datetime.now().date()
        for c in CALLS:
            c = dict(c)
            days_ago = c.pop("days_ago", 0)
            follow_in = c.pop("follow_up_in", None)
            c["call_date"] = (today - timedelta(days=days_ago)).isoformat()
            if follow_in is not None:
                c["follow_up_date"] = (today + timedelta(days=follow_in)).isoformat()
            c["notes"] = MARKER + " loaded by setup_samples.py - safe to delete"
            db.insert_record("SAL-009", c, created_by=c.get("agent_name") or "Team setup")
            calls_added += 1

    counts = {}
    for r in db.get_records("SAL-009")[0]:
        counts[r.get("contact_name") or "?"] = counts.get(r.get("contact_name") or "?", 0) + 1

    print("")
    print("=" * 66)
    print("  DHARANI 360 - sample data")
    print("=" * 66)
    print("\n  Chat messages added:  {}".format(chats_added))
    print("  Call records added:   {}".format(calls_added))
    if counts:
        print("\n  Calls now logged per contact:\n")
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            print("    {:<28} {} call{}".format(name, n, "s" if n != 1 else ""))
    print("\n  Open Chat and Calls in the sidebar to see them.")
    print("  Every sample call is tagged [sample] in its Notes so you can find")
    print("  and delete them once you have real activity.")
    print("=" * 66)
    print("")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                      # noqa: BLE001 - surfaced to the user
        print("\n  Sample data could not be loaded: {}".format(exc))
        sys.exit(1)
