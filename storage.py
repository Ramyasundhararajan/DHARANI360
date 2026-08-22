# -*- coding: utf-8 -*-
"""
DHARANI 360 - File storage
===========================
Scanned passports, trade licences and signed contracts are the evidence
behind the registers. An audit trail that points at files which no longer
exist is worth very little, so where those files live matters.

Two backends, one interface:

  * **local** (default) - `instance/uploads/...`, exactly as before. Right
    for a single PC.
  * **s3** - any S3-compatible object store: Supabase Storage, Cloudflare R2,
    Backblaze B2, Wasabi, AWS S3. Right the moment the app runs on a server,
    because a server's disk is disposable and its files should not be.

Nothing else in the codebase knows which is in use. db.py stores a *key*
("uploads/COR-002/14/ab12.pdf") and asks this module to put, get or delete it.

Switching on the object store - all four are required:

    S3_BUCKET=dharani360-files
    S3_ENDPOINT=https://<project>.storage.supabase.co/storage/v1/s3
    S3_ACCESS_KEY=...
    S3_SECRET_KEY=...
    S3_REGION=ap-south-1            (optional, defaults to us-east-1)

Then move what is already on disk:

    python migrate_files.py check     what would move
    python migrate_files.py upload    copy it up, then verify every file

Files are never deleted from disk by the migration. Confirm the remote copy
is good, keep the local one as a backup, and remove it yourself later.
"""
import config
import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

S3_BUCKET = config.get("S3_BUCKET", "")
S3_ENDPOINT = config.get("S3_ENDPOINT", "")
S3_ACCESS_KEY = config.get("S3_ACCESS_KEY", "")
S3_SECRET_KEY = config.get("S3_SECRET_KEY", "")
S3_REGION = config.get("S3_REGION", "us-east-1")


class StorageError(Exception):
    """The file could not be written, read or removed."""


class NotFound(StorageError):
    """No object with that key."""


# ---------------------------------------------------------------------------
# Local disk
# ---------------------------------------------------------------------------

class LocalBackend:
    name = "local"

    def __init__(self, root=None):
        import db
        self.root = root or db.INSTANCE_DIR

    def _path(self, key):
        # Keys are always relative and forward-slashed; refuse anything that
        # tries to climb out of the instance directory.
        clean = os.path.normpath(key).replace("\\", "/").lstrip("/")
        if clean.startswith("..") or ".." in clean.split("/"):
            raise StorageError("Refusing a key that escapes the storage root: {!r}".format(key))
        return os.path.join(self.root, *clean.split("/"))

    def put(self, key, data):
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        return key

    def get(self, key):
        try:
            with open(self._path(key), "rb") as fh:
                return fh.read()
        except FileNotFoundError:
            raise NotFound(key)
        except OSError as exc:
            raise StorageError(str(exc))

    def exists(self, key):
        return os.path.exists(self._path(key))

    def size(self, key):
        try:
            return os.path.getsize(self._path(key))
        except OSError:
            raise NotFound(key)

    def delete(self, key):
        try:
            os.remove(self._path(key))
            return True
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise StorageError(str(exc))

    def local_path(self, key):
        """A real path on disk, so the web server can stream it directly."""
        return self._path(key)


# ---------------------------------------------------------------------------
# S3-compatible object storage
# ---------------------------------------------------------------------------

class S3Backend:
    name = "s3"

    def __init__(self, bucket=None, endpoint=None, access_key=None,
                 secret_key=None, region=None):
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            raise StorageError(
                "S3 storage is configured but boto3 is not installed. "
                "Run: pip install boto3")

        self.bucket = bucket or S3_BUCKET
        if not self.bucket:
            raise StorageError("S3_BUCKET is not set.")

        self._client = boto3.client(
            "s3",
            endpoint_url=(endpoint or S3_ENDPOINT) or None,
            aws_access_key_id=access_key or S3_ACCESS_KEY,
            aws_secret_access_key=secret_key or S3_SECRET_KEY,
            region_name=region or S3_REGION,
            # Supabase Storage, R2 and B2 all want path-style addressing.
            config=BotoConfig(s3={"addressing_style": "path"},
                              retries={"max_attempts": 3, "mode": "standard"}),
        )

    def _err(self, exc):
        from botocore.exceptions import ClientError
        if isinstance(exc, ClientError):
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("NoSuchKey", "404", "NotFound"):
                return NotFound(str(exc))
        return StorageError(str(exc))

    def put(self, key, data):
        try:
            self._client.put_object(Bucket=self.bucket, Key=key, Body=data)
            return key
        except Exception as exc:
            raise self._err(exc)

    def get(self, key):
        try:
            obj = self._client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except Exception as exc:
            raise self._err(exc)

    def exists(self, key):
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def size(self, key):
        try:
            return self._client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        except Exception as exc:
            raise self._err(exc)

    def delete(self, key):
        try:
            self._client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            raise self._err(exc)

    def local_path(self, key):
        """Nothing is on this disk, so callers must stream the bytes instead."""
        return None


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

_backend = None


def configured_backend_name():
    """Which backend the settings ask for."""
    explicit = (config.get("STORAGE_BACKEND", "") or "").strip().lower()
    if explicit in ("local", "s3"):
        return explicit
    return "s3" if S3_BUCKET else "local"


def backend():
    """The backend in use, built once."""
    global _backend
    if _backend is None:
        if configured_backend_name() == "s3":
            _backend = S3Backend()
        else:
            _backend = LocalBackend()
    return _backend


def use(new_backend):
    """Swap the backend - for tests and for migrate_files.py."""
    global _backend
    previous, _backend = _backend, new_backend
    return previous


def reset():
    global _backend
    _backend = None


# Thin module-level API, so callers never touch the backend object.
def put(key, data):
    return backend().put(key, data)


def get(key):
    return backend().get(key)


def exists(key):
    return backend().exists(key)


def size(key):
    return backend().size(key)


def delete(key):
    return backend().delete(key)


def local_path(key):
    return backend().local_path(key)


def describe():
    name = configured_backend_name()
    if name == "s3":
        where = S3_ENDPOINT or "AWS S3"
        return "S3-compatible ({} / {})".format(where, S3_BUCKET)
    return "Local disk (instance/)"


def health():
    """Can we actually write and read? Used by /healthz and migrate_files.py."""
    probe = "healthcheck/.storage-probe"
    try:
        put(probe, b"ok")
        good = get(probe) == b"ok"
        delete(probe)
        return (True, "ok") if good else (False, "wrote but read back wrong")
    except Exception as exc:
        return False, str(exc)
