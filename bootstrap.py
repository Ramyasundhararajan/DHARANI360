# -*- coding: utf-8 -*-
"""
DHARANI 360 - first run on a new machine or a new deployment
============================================================
Creates the tables, creates the team, links their work emails, and then
checks that at least one person can actually sign in before it finishes.

Run once after deploying:      python bootstrap.py

Safe to run again - it never overwrites an account that already exists,
and it will refuse to leave the system with nobody able to get in.

Why this exists
---------------
setup_signin.py deactivates every account that is not on the allowlist.
On a brand new database the five team accounts do not exist yet, so
running it first would disable the seeded administrator and leave the
system permanently locked. This script enforces the right order.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import db          # noqa: E402
import auth        # noqa: E402


def line(msg=""):
    print("  " + msg)


def main():
    print("\n" + "=" * 62)
    print("  DHARANI 360 - first-run setup")
    print("=" * 62 + "\n")

    line("1. Creating tables...")
    db.init_db()
    line("   done.")

    line("")
    line("2. Creating the team...")
    import setup_team
    try:
        setup_team.main()
    except SystemExit:
        pass
    except AttributeError:
        line("   setup_team.py has no main() - run it on its own.")

    line("")
    line("3. Linking work emails...")
    import setup_signin
    sys.argv = ["setup_signin.py", "--local-only"]
    try:
        setup_signin.main()
    except SystemExit:
        pass
    except AttributeError:
        line("   setup_signin.py has no main() - run it on its own.")

    line("")
    line("4. Checking somebody can sign in...")
    users = [u for u in db.list_users() if u["active"] and u["email"]]
    if users:
        line("   {} account(s) ready:".format(len(users)))
        for u in users:
            line("     {:<28} {}".format(u["email"], u["role"]))
        print("\n" + "=" * 62 + "\n")
        return 0

    # Nothing can sign in. Rather than leave a locked system, put the
    # administrator back and say so loudly.
    line("   NOTHING CAN SIGN IN. Restoring the administrator.")
    admin = db.get_user_by_username("admin")
    if admin:
        db.set_user_active(admin["id"], True)
        line("   'admin' re-enabled. Sign in and create the real accounts")
        line("   from Users & Access, then run this script again.")
    else:
        line("   No administrator account exists either. Delete")
        line("   instance/dharani360.db and run this script again.")
    print("\n" + "=" * 62 + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
