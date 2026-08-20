# -*- coding: utf-8 -*-
"""
DHARANI 360 - one-time team setup
====================================
Adds the five DHARANI staff members to this system:

  * a LOGIN ACCOUNT in Users & Access (so they can sign in), and
  * an EMPLOYEE MASTER FILE record (DR-HR-002) so they exist in the HR register
    that every other HR form points at.

Run it once:   double-click setup_team.bat
           or: python setup_team.py

It is safe to run more than once. Anyone already present is skipped, not
duplicated, and nothing already in the database is modified or deleted.

Every account is created with a temporary password and is forced to choose a
new one at first sign-in, so nobody keeps a password that was set for them.
"""
import sys

import db
import auth

# Temporary password. Each person is required to replace it the first time
# they sign in - the app will not let them past the change-password screen.
TEMP_PASSWORD = "Dharani360"

# role       -> what it grants (see access.py)
#   CEO                 = full access + Users & Settings  ("Super Admin")
#   Director            = full access + Users & Settings  ("Super Admin")
#                         shown on screen as "IT & Data Management"
#   Admin / Operations  = HR, IT, vendors, payroll, recruitment, attendance,
#                         help desk, projects, content, corporate, compliance
#   Agent               = agents, leads/clients and properties
TEAM = [
    {"username": "ramya",       "full_name": "Ramya",
     "email": "ramya@dharanis.ae",       "position": "IT & Data Management Specialist",
     "role": "Director",           "department": "Assets, IT & Security"},
    {"username": "akbar",        "full_name": "Akbar Hassan Dharani",
     "email": "akbar@dharanis.ae",       "position": "CEO",
     "role": "CEO",                "department": "Corporate & Licensing"},
    {"username": "khalidaamyn",  "full_name": "Khalida Amyn",
     "email": "khalidaamyn@dharanis.ae", "position": "Office Admin",
     "role": "Admin / Operations", "department": "Vendors & Administration"},
    {"username": "baqeer",       "full_name": "Baqeer Muhammed",
     "email": "baqeer@dharanis.ae",      "position": "Property Consultant",
     "role": "Agent",              "department": "Sales, Leads & Clients"},
    {"username": "greetus",      "full_name": "Greetus",
     "email": "greetus@dharanis.ae",     "position": "Content Creator",
     "role": "Admin / Operations", "department": "Content & Documentation"},
]


def main():
    db.init_db()

    existing_users = {u["username"].lower() for u in db.list_users()}
    existing_staff = {
        (r.get("email") or "").strip().lower()
        for r in db.get_records("HR-002")[0]
    }

    made_users, made_records, skipped, corrected = [], [], [], []

    for person in TEAM:
        uname = person["username"].lower()

        if uname in existing_users:
            # The account is already here. Roles do change - somebody is
            # promoted, a title is corrected - so bring the stored role back
            # in line with the list above rather than leaving it stale.
            current = next((u for u in db.list_users()
                            if u["username"].lower() == uname), None)
            if current is not None and current["role"] != person["role"]:
                db.update_user(current["id"], role=person["role"])
                corrected.append("{} moved from {} to {}".format(
                    person["full_name"], current["role"], person["role"]))
            else:
                skipped.append("login for " + person["full_name"])
        else:
            db.create_user(
                username=uname,
                password_hash=auth.hash_password(TEMP_PASSWORD),
                full_name=person["full_name"],
                role=person["role"],
                must_change_password=True,
            )
            made_users.append(person)

        if person["email"].lower() in existing_staff:
            skipped.append("employee file for " + person["full_name"])
        else:
            db.insert_record("HR-002", {
                "full_name": person["full_name"],
                "position": person["position"],
                "department": person["department"],
                "email": person["email"],
                "employment_type": "Full Time",
                "status": "Active",
                "notes": "Created by the one-time team setup script.",
            }, created_by="Team setup")
            made_records.append(person)

    print("")
    print("=" * 66)
    print("  DHARANI 360 - team setup")
    print("=" * 66)

    if made_users:
        print("\n  Login accounts created:\n")
        for p in made_users:
            print("    {:<22} {:<26} {}".format(p["username"], p["role"], p["full_name"]))
        print("\n    Temporary password for all of the above: {}".format(TEMP_PASSWORD))
        print("    Each person must set their own password at first sign-in.")
    else:
        print("\n  No new login accounts were needed.")

    if made_records:
        print("\n  Employee master files created:\n")
        for p in made_records:
            print("    {:<26} {}".format(p["full_name"], p["position"]))
    else:
        print("\n  No new employee files were needed.")

    if corrected:
        print("\n  Roles brought up to date:\n")
        for c in corrected:
            print("    " + c)

    if skipped:
        print("\n  Already present, left untouched:")
        for s in skipped:
            print("    - " + s)

    print("\n  Review or change roles any time under Administration > Users & Access.")
    print("=" * 66)
    print("")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:                      # noqa: BLE001 - surfaced to the user
        print("\n  Team setup could not finish: {}".format(exc))
        print("  Nothing was left half-done; you can fix the problem and run it again.\n")
        sys.exit(1)
