# -*- coding: utf-8 -*-
"""
DHARANI 360 - Request security
===============================
Three things, applied to every request, that a single-PC install could do
without and a system reachable over a network cannot:

  1. CSRF protection. Without it, a page on another website can quietly make
     your browser submit a form here - deleting a record, creating a user -
     using the session you already have open. Every POST must now carry a
     token that only this site could have given you.

  2. Session cookie hardening. The login cookie is marked HttpOnly (scripts
     cannot read it), SameSite=Lax (it is not sent on cross-site requests),
     and Secure when the site is served over HTTPS.

  3. A small set of response headers that stop the site being framed by
     another page or having its content type second-guessed.

Environment variables:

    SECURE_COOKIES=1|0     Force Secure cookies on or off. Default: on when
                           the app looks hosted (DATABASE_URL or SECRET_KEY
                           set in the environment), off for a local PC.
    SESSION_HOURS=12       How long a login lasts before it must be renewed.
"""
import os
import secrets
from datetime import timedelta

from flask import request, session, abort, g

#: Methods that cannot change anything, so they need no token.
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}

#: Endpoints that legitimately receive a POST without a session-issued token.
#: Keep this list short and justify every entry.
CSRF_EXEMPT_ENDPOINTS = set()

SESSION_KEY = "_csrf_token"
FORM_FIELD = "_csrf"
HEADER_NAME = "X-CSRF-Token"


def _env_flag(name, default=False):
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def looks_hosted():
    """True when this process is running as a deployed service, not on a desk."""
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("SECRET_KEY"))


def csrf_token():
    """The token for this session, minted once and reused."""
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[SESSION_KEY] = token
    return token


def _submitted_token():
    return (request.form.get(FORM_FIELD)
            or request.headers.get(HEADER_NAME)
            or request.args.get(FORM_FIELD)
            or "")


def init_security(app):
    """Apply all of the above to a Flask app."""

    secure_cookies = _env_flag("SECURE_COOKIES", default=looks_hosted())
    try:
        session_hours = int(os.environ.get("SESSION_HOURS") or 12)
    except ValueError:
        session_hours = 12

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure_cookies,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=session_hours),
        # A signed-in person stays signed in while they keep working, rather
        # than being thrown out mid-form exactly `session_hours` after login.
        SESSION_REFRESH_EACH_REQUEST=True,
    )

    @app.before_request
    def _csrf_protect():
        if request.method in SAFE_METHODS:
            return None
        if request.endpoint in CSRF_EXEMPT_ENDPOINTS:
            return None
        if getattr(app.view_functions.get(request.endpoint, None), "_csrf_exempt", False):
            return None

        expected = session.get(SESSION_KEY)
        submitted = _submitted_token()
        if not expected or not submitted or not secrets.compare_digest(str(expected), str(submitted)):
            # 400 rather than 403: the request is malformed, and saying so
            # plainly is more useful than implying the person lacks permission.
            abort(400, description=(
                "This form was not submitted from a current DHARANI 360 page, "
                "or your session expired while it was open. Reload the page "
                "and try again."))
        return None

    @app.before_request
    def _mark_session_permanent():
        session.permanent = True

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if secure_cookies:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # Available in every template as {{ csrf_token() }} and, for pages that
    # post with fetch(), as {{ csrf_token() }} in an X-CSRF-Token header.
    app.jinja_env.globals["csrf_token"] = csrf_token

    return app


def csrf_exempt(view):
    """Decorator. Use only where a token genuinely cannot be presented."""
    view._csrf_exempt = True
    return view


def client_ip():
    """The caller's address, honouring one proxy hop when hosted.

    Only the first entry of X-Forwarded-For is used, and only when the app
    looks hosted - otherwise anyone could set the header and write a false
    address into the audit trail.
    """
    if looks_hosted():
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote_addr
