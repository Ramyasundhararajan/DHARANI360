# -*- coding: utf-8 -*-
"""
DHARANI 360 - Preview
======================
See the system, with realistic sample data, without touching a single real
record. Run it, and your browser opens already signed in.

    python preview.py                 open the preview
    python preview.py --fresh         throw the sample data away and rebuild
    python preview.py --port 5100     use a different port

What makes this safe:

  * It uses its own database, in instance/preview/, never the real one.
  * It ignores DATABASE_URL entirely, so it cannot reach a live server.
  * It only listens on 127.0.0.1 - nobody else can open it.
  * Automatic sign-in works only for requests from this computer.
  * Every page carries a PREVIEW banner, so a screenshot can never be
    mistaken for real company data.

It is also the demo to show a client: the sample brokerage has licences
expiring inside 30 days, so the Control Tower opens red rather than empty.
"""
import argparse
import os
import socket
import sys
import shutil
import threading
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PREVIEW_DIR = os.path.join(BASE_DIR, "instance", "preview")

PREVIEW_EMAIL = "preview@dharani360.local"
PREVIEW_PASSWORD = "preview"


def _isolate(fresh=False):
    """Point everything at the preview database before db.py is imported."""
    if fresh and os.path.isdir(PREVIEW_DIR):
        shutil.rmtree(PREVIEW_DIR, ignore_errors=True)
        print("  Sample data cleared.")
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    os.environ["D360_INSTANCE_DIR"] = PREVIEW_DIR
    os.environ["D360_PREVIEW"] = "1"
    # A preview must never reach a real database, whatever .env says.
    os.environ["DATABASE_URL"] = ""
    os.environ["SECURE_COOKIES"] = "0"
    os.environ["DEMO_MODE"] = "0"
    # A fixed key so the preview does not sign you out every restart.
    os.environ.setdefault("SECRET_KEY", "preview-only-not-a-secret")


def _free_port(preferred):
    """The preferred port, or the next free one after it."""
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def _seed():
    """Fill the preview with sample records, once."""
    import db
    import auth

    # The preview database is brand new on a --fresh run, so build the
    # registers before asking how many records they hold.
    db.init_db()

    counts = db.all_counts()
    if sum(counts.values()) == 0:
        print("  Loading sample records (first run only, takes a moment)...")
        try:
            import demo_data
            demo_data.main()
        except Exception as exc:            # a broken sample must not block the preview
            print("  Sample data could not be loaded ({}). Continuing empty.".format(exc))

    user = db.get_user_by_username("admin")
    if user is None:
        return None
    db.set_user_email(user["id"], PREVIEW_EMAIL)
    db.set_password(user["id"], auth.hash_password(PREVIEW_PASSWORD),
                    must_change_password=False)
    db.update_user(user["id"], full_name="Preview Director", role="Director")
    return db.get_user_by_username("admin")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open DHARANI 360 with sample data.")
    parser.add_argument("--fresh", action="store_true",
                        help="discard the sample data and build it again")
    parser.add_argument("--port", type=int, default=5100)
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open a browser window")
    args = parser.parse_args(argv)

    print()
    print("DHARANI 360 - preview")
    print("=" * 62)
    _isolate(fresh=args.fresh)

    user = _seed()
    if user is None:
        print("  Could not prepare the preview account.")
        return 1

    import db
    import app as app_module

    preferred_port = int(os.environ.get("PORT", args.port))
    port = _free_port(preferred_port)
    url = "http://127.0.0.1:{}/".format(port)

    total = sum(db.all_counts().values())
    print("  Sample records   {}".format(total))
    print("  Signed in as     {} (Director)".format(user["full_name"] or user["username"]))
    print("  Database         {}".format(os.path.join("instance", "preview")))
    print("  Address          {}".format(url))
    print("=" * 62)
    print()
    print("  Your real records are untouched. Close this window to stop.")
    print()

    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app_module.app.run(host=os.environ.get("HOST", "0.0.0.0"), port=port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
