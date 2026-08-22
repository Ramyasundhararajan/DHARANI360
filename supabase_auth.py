# -*- coding: utf-8 -*-
"""
DHARANI 360 - Supabase sign-in
==================================================================
Authentication is delegated to Supabase Auth; authorisation stays local.

That split is deliberate. Supabase answers one question - "is this person who
they say they are?" - by checking the email and password against the project's
auth.users table. Everything after that (which role they hold, which
departments they may open, whose name goes on a record) continues to come from
the local users table, because that is what every other part of this system
already reads.

Sign-in is additionally restricted to an explicit allowlist of addresses. A
person must be in that list AND have a matching local account AND authenticate
successfully with Supabase. Any one of the three failing is a refusal - so a
stray account created in the Supabase dashboard cannot, on its own, get into
this system.

Configuration lives in supabase_config.json next to this file (see
supabase_config.example.json). That file holds the project URL and the
publishable anon key only. The service-role key is never read here and must
never be placed in it - only the one-time provisioning script asks for that,
and it asks for it locally.
"""
import config
import json
import os
import time
import urllib.error
import urllib.request

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "supabase_config.json")

# Addresses permitted to sign in. This is the authoritative list: it is checked
# before Supabase is contacted and again after it answers.
#
# A hosted deployment sets ALLOWED_EMAILS in the environment (see .env.example)
# so the list can change without editing code. With nothing set, the built-in
# list below applies, and an existing installation keeps working untouched.
DEFAULT_ALLOWED_EMAILS = [
    "akbar@dharanis.ae",
    "ramya@dharanis.ae",
    "khalidaamyn@dharanis.ae",
    "baqeer@dharanis.ae",
    "greetus@dharanis.ae",
]

ALLOWED_EMAILS = config.ALLOWED_EMAILS or DEFAULT_ALLOWED_EMAILS

_ALLOWED_SET = {e.lower() for e in ALLOWED_EMAILS}

_TIMEOUT_SECONDS = 8


class SupabaseNotConfigured(Exception):
    """Raised when supabase_config.json is missing or incomplete."""


class SupabaseUnreachable(Exception):
    """Raised when the project cannot be contacted (offline, DNS, timeout)."""


def is_allowed(email):
    return (email or "").strip().lower() in _ALLOWED_SET


def load_config():
    """Project URL and anon key, or None if not configured yet.

    The environment wins over the file. A hosted deployment sets SUPABASE_URL
    and SUPABASE_ANON_KEY and ships no secrets file at all; a local PC keeps
    using supabase_config.json exactly as before.
    """
    if config.SUPABASE_URL and config.SUPABASE_ANON_KEY:
        cfg = {"url": config.SUPABASE_URL,
               "anon_key": config.SUPABASE_ANON_KEY,
               "offline_fallback": config.flag("SUPABASE_OFFLINE_FALLBACK", True)}
    else:
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError):
            return None
    url = (cfg.get("url") or "").strip().rstrip("/")
    key = (cfg.get("anon_key") or "").strip()
    if not url or not key or url.startswith("https://YOUR-"):
        return None
    cfg["url"] = url
    cfg["anon_key"] = key
    return cfg


def is_configured():
    return load_config() is not None


def offline_fallback_enabled():
    """Whether a cached local password may be accepted when Supabase is down.

    DHARANI 360 is used on a single office machine that is not always online,
    and an authentication service that is unreachable would otherwise mean
    nobody can open the system at all. When this is on, a successful Supabase
    sign-in refreshes the local password hash, and that hash is accepted only
    while Supabase itself cannot be reached. Set "offline_fallback": false in
    supabase_config.json to require Supabase every time.
    """
    cfg = load_config()
    return True if cfg is None else bool(cfg.get("offline_fallback", True))


def sign_in(email, password):
    """Verify one credential pair against Supabase Auth.

    Returns the decoded Supabase user object on success.
    Raises SupabaseNotConfigured, SupabaseUnreachable, or ValueError (bad
    credentials / not allowed).
    """
    email = (email or "").strip()
    if not is_allowed(email):
        raise ValueError("This address is not permitted to sign in.")

    cfg = load_config()
    if cfg is None:
        raise SupabaseNotConfigured("supabase_config.json is missing or incomplete.")

    endpoint = "{}/auth/v1/token?grant_type=password".format(cfg["url"])
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "apikey": cfg["anon_key"],
            "Authorization": "Bearer {}".format(cfg["anon_key"]),
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        # 400 and 401 are Supabase saying "no" - a real answer, not an outage.
        if err.code in (400, 401, 403):
            raise ValueError("Incorrect email or password.")
        raise SupabaseUnreachable("Supabase returned HTTP {}.".format(err.code))
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise SupabaseUnreachable(str(err))

    user = body.get("user") or {}
    returned = (user.get("email") or "").strip().lower()
    # Belt and braces: never trust the response to be for the address asked for.
    if returned != email.lower() or not is_allowed(returned):
        raise ValueError("Incorrect email or password.")
    return user


def health():
    """A short human-readable status line for the Settings page."""
    cfg = load_config()
    if cfg is None:
        return {"ok": False, "state": "not-configured",
                "detail": "supabase_config.json has not been filled in yet."}
    try:
        request = urllib.request.Request(
            "{}/auth/v1/health".format(cfg["url"]),
            headers={"apikey": cfg["anon_key"]},
        )
        started = time.time()
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            response.read()
        return {"ok": True, "state": "reachable",
                "detail": "Responded in {} ms.".format(int((time.time() - started) * 1000)),
                "url": cfg["url"]}
    except Exception as err:  # noqa: BLE001 - any failure is "unreachable" here
        return {"ok": False, "state": "unreachable", "detail": str(err), "url": cfg["url"]}
