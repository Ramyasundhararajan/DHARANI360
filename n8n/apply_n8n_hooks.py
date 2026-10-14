"""Wire DHARANI 360's registers to n8n - three small edits to db.py.

    python apply_n8n_hooks.py            show what it would change
    python apply_n8n_hooks.py --write    make the change (keeps db.py.bak)
    python apply_n8n_hooks.py --undo     put the original back

It is idempotent: running it twice changes nothing the second time. It never
touches your data, only db.py, and it takes a .bak copy before writing.

After running it with --write, add to .env:

    N8N_BASE_URL=https://your-n8n-host
    N8N_EVENT_TOKEN=<python -c "import secrets; print(secrets.token_urlsafe(32))">

then restart the portal and run:  python n8n_hooks.py
"""

import os
import shutil
import sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db.py")

IMPORT_ANCHOR = "import dbcompat\n"
IMPORT_PATCH = """import dbcompat
try:                       # n8n event hook - absent or unconfigured is fine
    import n8n_hooks
except Exception:          # pragma: no cover
    class n8n_hooks:       # noqa: N801 - a stand-in that does nothing
        @staticmethod
        def emit(*a, **k):
            pass
"""

INSERT_ANCHOR = """    conn.commit()
    conn.close()
    return doc_no
"""
INSERT_PATCH = """    conn.commit()
    conn.close()
    n8n_hooks.emit("record.created", form_code, new_id, doc_no,
                   data, actor=created_by)
    return doc_no
"""

UPDATE_ANCHOR = """        record_audit_many(changes, conn=conn)
    conn.commit()
    conn.close()
"""
UPDATE_PATCH = """        record_audit_many(changes, conn=conn)
    conn.commit()
    conn.close()
    if changes:
        n8n_hooks.emit("record.changed", form_code, record_id,
                       (before["doc_no"] if before is not None else None),
                       data,
                       changed_fields={c["field_name"]: c["new_value"]
                                       for c in changes})
"""

DELETE_ANCHOR = """    conn.commit()
    conn.close()
    for att in get_attachments(form_code, record_id):
"""
DELETE_PATCH = """    conn.commit()
    conn.close()
    n8n_hooks.emit("record.deleted", form_code, record_id,
                   (before["doc_no"] if before is not None else None), {})
    for att in get_attachments(form_code, record_id):
"""

EDITS = [("import", IMPORT_ANCHOR, IMPORT_PATCH),
         ("insert_record", INSERT_ANCHOR, INSERT_PATCH),
         ("update_record", UPDATE_ANCHOR, UPDATE_PATCH),
         ("delete_record", DELETE_ANCHOR, DELETE_PATCH)]


def main():
    write = "--write" in sys.argv
    undo = "--undo" in sys.argv

    if undo:
        if not os.path.exists(DB + ".bak"):
            print("No db.py.bak here - nothing to undo.")
            return 1
        shutil.copy2(DB + ".bak", DB)
        print("db.py restored from db.py.bak.")
        return 0

    if not os.path.exists(DB):
        print("db.py is not in this folder. Put apply_n8n_hooks.py and "
              "n8n_hooks.py next to db.py and run it again.")
        return 1

    src = open(DB, encoding="utf-8").read()
    todo, done = [], []
    for name, anchor, patch in EDITS:
        if patch.strip() in src:
            done.append(name)
        elif anchor in src:
            todo.append((name, anchor, patch))
        else:
            print("! could not find the %s anchor - db.py has moved on since "
                  "this patcher was written. Apply that one by hand." % name)

    if done:
        print("Already wired:", ", ".join(done))
    if not todo:
        print("Nothing left to do.")
        return 0

    print("Would change:", ", ".join(t[0] for t in todo))
    if not write:
        print("\nRun again with --write to apply.")
        return 0

    shutil.copy2(DB, DB + ".bak")
    for _, anchor, patch in todo:
        src = src.replace(anchor, patch, 1)
    open(DB, "w", encoding="utf-8").write(src)
    print("\ndb.py updated. Original kept as db.py.bak.")
    print("Now: set N8N_BASE_URL in .env, restart the portal, "
          "then run  python n8n_hooks.py  to send a test event.")
    print("Check nothing broke:  python smoketest.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
