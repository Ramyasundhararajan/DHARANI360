# -*- coding: utf-8 -*-
"""
DHARANI 360 - one-time sign-in setup
=============================================================================
Run this ONCE, after filling in supabase_config.json. It does two things:

  1. In Supabase  - creates the five permitted accounts with their passwords,
                    already email-confirmed so nobody has to click a link.
  2. Locally      - attaches each address to its existing DHARANI 360 account
                    and deactivates every account that is not on the list,
                    including 'admin'.

    python setup_signin.py

Existing records, departments and registers are untouched. Only the users
table is written to.

-----------------------------------------------------------------------------
ABOUT THE SERVICE-ROLE KEY
-----------------------------------------------------------------------------
Creating users through the Supabase Admin API needs the service_role key,
which can read and write anything in the project. This script asks for it at
the prompt, uses it for the few seconds it runs, and never writes it to disk.

Do not paste it into supabase_config.json, do not email it, and do not leave
it in a file inside this folder - this folder syncs to OneDrive. If it ever
leaks, rotate it in the dashboard under Project Settings -> API.

If you would rather not handle the key at all, create the five users by hand
in the dashboard (Authentication -> Users -> Add user, tick "Auto Confirm
User") and then run this script with --local-only to do just the local half.
"""
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auth
import db
import supabase_auth

# email -> (existing DHARANI 360 username, password to set in Supabase)
ACCOUNTS = [
    ("akbar@dharanis.ae",       "akbar",       "Dharani@2024"),
    ("ramya@dharanis.ae",       "ramya",       "Ramya@2024"),
    ("khalidaamyn@dharanis.ae", "khalidaamyn", "Khalida@2024"),
    ("baqeer@dharanis.ae",      "baqeer",      "Baqeer@2024"),
    ("greetus@dharanis.ae",     "greetus",     "Greetus@2024"),
]


def create_supabase_user(base_url, service_key, email, password):
    """Create (or update) one confirmed user through the Admin API."""
    payload = json.dumps({
        "email": email,
        "password": password,
        "email_confirm": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        "{}/auth/v1/admin/users".format(base_url),
        data=payload,
        method="POST",
        headers={
            "apikey": service_key,
            "Authorization": "Bearer {}".format(service_key),
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            json.loads(response.read().decode("utf-8"))
        return "created"
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")
        if err.code in (409, 422) or "already" in detail.lower():
            return "exists"
        raise RuntimeError("HTTP {} - {}".format(err.code, detail[:300]))


def main():
    local_only = "--local-only" in sys.argv

    print("DHARANI 360 - sign-in setup")
    print("=" * 60)

    db.init_db()

    # ---------------------------------------------------------- Supabase --
    if not local_only:
        cfg = supabase_auth.load_config()
        if cfg is None:
            print("\nsupabase_config.json is missing or still has placeholder values.")
            print("Copy supabase_config.example.json to supabase_config.json and fill")
            print("in the project URL and the anon key first. See SUPABASE_SETUP.md.")
            return 1

        print("\nProject: {}".format(cfg["url"]))
        print("\nPaste the service_role key (Project Settings -> API -> service_role).")
        print("It is used only for this run and is never saved to disk.")
        service_key = getpass.getpass("service_role key: ").strip()
        if not service_key:
            print("No key given - nothing was done.")
            return 1

        print("\nCreating Supabase accounts:")
        for email, _username, password in ACCOUNTS:
            try:
                result = create_supabase_user(cfg["url"], service_key, email, password)
                print("  {:<26} {}".format(email, result))
            except RuntimeError as err:
                print("  {:<26} FAILED - {}".format(email, err))

    # ------------------------------------------------------------- local --
    print("\nLinking local accounts:")
    allowed_ids = []
    for email, username, _password in ACCOUNTS:
        user = db.get_user_by_username(username)
        if not user:
            print("  {:<26} no local account named '{}' - skipped".format(email, username))
            continue
        db.set_user_email(user["id"], email)
        # The cached hash is what the offline fallback checks, so seed it now
        # rather than waiting for the first online sign-in.
        db.set_password(user["id"], auth.hash_password(_password), must_change_password=False)
        db.set_user_active(user["id"], True)
        allowed_ids.append(user["id"])
        print("  {:<26} -> {} ({})".format(email, user["username"], user["role"]))

    print("\nDeactivating every other account:")
    disabled = 0
    for user in db.list_users():
        if user["id"] in allowed_ids:
            continue
        if user["active"]:
            db.set_user_active(user["id"], False)
            disabled += 1
            print("  {:<26} disabled".format(user["username"]))
    if not disabled:
        print("  (none)")

    print("\nDone. {} account(s) can sign in.".format(len(allowed_ids)))
    if not local_only:
        print("\nDelete nothing else, but do close this window - the service_role key")
        print("may still be in your clipboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
