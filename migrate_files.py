# -*- coding: utf-8 -*-
"""
DHARANI 360 - Move attachments into object storage
===================================================
    python migrate_files.py check      what is on disk, and is the store reachable
    python migrate_files.py upload     copy it up, then read every file back
    python migrate_files.py verify     confirm every attachment is in the store

Nothing is ever deleted from disk. The local copies stay exactly where they
are, so a failed or half-finished migration costs you nothing. Once `verify`
is clean and you have a backup, remove `instance/uploads/` yourself.

Requires the S3 settings from storage.py to be configured - see .env.example.
"""
import config  # noqa: F401
import sys

import storage


def _say(msg=""):
    print(msg, flush=True)


def _attachments():
    """Every attachment row, with the key it should live under."""
    import db
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT id, form_code, record_id, original_name, stored_name, size_bytes "
        "FROM attachments ORDER BY id").fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "name": r["original_name"],
            "key": db.attachment_key(r["form_code"], r["record_id"], r["stored_name"]),
            "size": r["size_bytes"] or 0,
        })
    return out


def _local():
    """A LocalBackend, whatever the configured backend happens to be."""
    return storage.LocalBackend()


def check():
    _say("DHARANI 360 - attachment storage")
    _say("=" * 66)
    _say("  Configured backend  {}".format(storage.describe()))

    rows = _attachments()
    local = _local()
    on_disk = [a for a in rows if local.exists(a["key"])]
    total = sum(a["size"] for a in on_disk)

    _say("  Attachments on file {}".format(len(rows)))
    _say("  Present on disk     {} ({:,} bytes)".format(len(on_disk), total))
    missing_locally = [a for a in rows if not local.exists(a["key"])]
    if missing_locally:
        _say("  Recorded but absent {}  <- these files are already gone".format(len(missing_locally)))

    if storage.configured_backend_name() != "s3":
        _say()
        _say("  Object storage is not configured, so there is nothing to migrate to.")
        _say("  Set S3_BUCKET, S3_ENDPOINT, S3_ACCESS_KEY and S3_SECRET_KEY first.")
        return 1

    ok, detail = storage.health()
    _say("  Object store        {}".format("reachable" if ok else "NOT reachable - " + detail))
    if not ok:
        return 1

    already = [a for a in on_disk if storage.exists(a["key"])]
    _say("  Already uploaded    {}".format(len(already)))
    _say("  To upload           {}".format(len(on_disk) - len(already)))
    _say()
    if len(already) < len(on_disk):
        _say("  Ready. Take a backup, then: python migrate_files.py upload")
        return 1
    _say("  Nothing to do.")
    return 0


def upload():
    if storage.configured_backend_name() != "s3":
        _say("Object storage is not configured. Nothing to upload to.")
        return 1

    ok, detail = storage.health()
    if not ok:
        _say("The object store is not reachable: {}".format(detail))
        return 1

    rows = _attachments()
    local = _local()
    remote = storage.backend()

    _say("Uploading attachments to {}".format(storage.describe()))
    _say()

    copied = skipped = absent = failed = 0
    for a in rows:
        if not local.exists(a["key"]):
            absent += 1
            continue
        if remote.exists(a["key"]):
            skipped += 1
            continue
        try:
            data = local.get(a["key"])
            remote.put(a["key"], data)
            # Read it straight back: an upload that reported success and did
            # not land is the failure mode worth spending a round trip on.
            if remote.get(a["key"]) != data:
                raise storage.StorageError("uploaded but read back different")
            copied += 1
            _say("  + {:<44} {:>9,} bytes".format(a["name"][:44], len(data)))
        except Exception as exc:
            failed += 1
            _say("  ! {:<44} FAILED: {}".format(a["name"][:44], exc))

    _say()
    _say("  copied {}   already there {}   already missing {}   failed {}"
         .format(copied, skipped, absent, failed))
    _say()
    if failed:
        _say("  Some files did not upload. Nothing was deleted - run this again.")
        return 1
    _say("  Now confirm: python migrate_files.py verify")
    _say("  The local copies are untouched. Keep them until you have verified.")
    return 0


def verify():
    if storage.configured_backend_name() != "s3":
        _say("Object storage is not configured.")
        return 1

    rows = _attachments()
    remote = storage.backend()
    local = _local()

    missing, wrong_size, gone_everywhere = [], [], []
    for a in rows:
        if not remote.exists(a["key"]):
            (gone_everywhere if not local.exists(a["key"]) else missing).append(a)
            continue
        if a["size"] and remote.size(a["key"]) != a["size"]:
            wrong_size.append(a)

    _say("Verifying {} attachment(s) against {}".format(len(rows), storage.describe()))
    _say()
    _say("  in the store and the right size   {}".format(
        len(rows) - len(missing) - len(wrong_size) - len(gone_everywhere)))
    if missing:
        _say("  on disk but NOT uploaded          {}".format(len(missing)))
        for a in missing[:10]:
            _say("      {}".format(a["name"]))
    if wrong_size:
        _say("  uploaded at the wrong size        {}".format(len(wrong_size)))
        for a in wrong_size[:10]:
            _say("      {}".format(a["name"]))
    if gone_everywhere:
        _say("  recorded but the file is gone     {}".format(len(gone_everywhere)))
        _say("      (these were already lost before the migration)")

    _say()
    if missing or wrong_size:
        _say("  Not finished. Run: python migrate_files.py upload")
        return 1
    _say("  Every attachment that still exists is in the object store.")
    _say("  Keep instance/uploads/ until your next verified backup, then remove it.")
    return 0


USAGE = "Usage: python migrate_files.py [check|upload|verify]"


def main(argv):
    cmd = (argv[1] if len(argv) > 1 else "check").lower()
    if cmd == "check":
        return check()
    if cmd == "upload":
        return upload()
    if cmd == "verify":
        return verify()
    _say(USAGE)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
