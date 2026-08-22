# -*- coding: utf-8 -*-
"""
DHARANI 360 - Health and logging
=================================
Two things you only appreciate the first time something breaks at 9pm.

**A health check.** GET /healthz answers in JSON whether the system is
actually working - not just whether the web server replied, but whether it
can reach the database. Point any free uptime monitor at it (UptimeRobot,
Better Stack, Cronitor, Healthchecks.io) and you find out it is down before
a client tells you. It needs no sign-in, and deliberately reveals nothing:
no version numbers, no connection strings, no record counts.

**Error logging.** When a page fails, the person sees a short reference code
and you get the full traceback - with the URL, the signed-in user and that
same code - written to instance/logs/errors.log. "It broke" becomes "show me
reference A7F3C2", which is one grep away from the answer.

Logs rotate at 2MB and keep five files, so they can never fill the disk.
"""
import logging
import os
import secrets
import traceback
from logging.handlers import RotatingFileHandler

from flask import request, jsonify, render_template

LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 5


def _log_dir():
    import db
    path = os.path.join(db.INSTANCE_DIR, "logs")
    os.makedirs(path, exist_ok=True)
    return path


def init_logging(app):
    """Send application errors to instance/logs/errors.log as well as stderr."""
    log_path = os.path.join(_log_dir(), "errors.log")

    handler = RotatingFileHandler(log_path, maxBytes=LOG_MAX_BYTES,
                                  backupCount=LOG_BACKUPS, encoding="utf-8")
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Werkzeug's own errors should land in the same file.
    logging.getLogger("werkzeug").addHandler(handler)

    app.config["ERROR_LOG_PATH"] = log_path
    return log_path


def reference_code():
    """A short code the person can quote and you can grep for."""
    return secrets.token_hex(3).upper()


def init_error_handling(app):
    """Log every unhandled exception with enough context to fix it."""

    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def _unhandled(exc):
        # Flask re-raises HTTP errors through here too; those already have
        # their own handlers and pages, so let them past untouched.
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc

        ref = reference_code()
        try:
            import auth
            user = auth.current_user()
            who = user["username"] if user else "(not signed in)"
        except Exception:
            who = "(unknown)"

        app.logger.error(
            "reference=%s  %s %s  user=%s  ip=%s\n%s",
            ref, request.method, request.path, who, request.remote_addr,
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))

        return render_template(
            "error.html", code=500,
            message="Something went wrong on our side, and it has been written "
                    "to the error log. Quote reference {} when reporting it.".format(ref)
        ), 500

    return app


def init_health(app):
    """Add /healthz - the address an uptime monitor should watch."""

    @app.route("/healthz")
    def healthz():
        import db
        import dbcompat

        checks = {}
        ok = True

        try:
            conn = db.get_conn()
            conn.execute("SELECT 1").fetchone()
            conn.close()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unreachable"
            ok = False
            app.logger.error("health check: database unreachable\n%s",
                             traceback.format_exc())

        try:
            writable = os.access(db.INSTANCE_DIR, os.W_OK)
            checks["storage"] = "ok" if writable else "not writable"
            ok = ok and writable
        except Exception:
            checks["storage"] = "unknown"
            ok = False

        # Deliberately no version, no engine name, no counts: this endpoint is
        # public, and a health check is not a place to describe the system.
        body = {"status": "ok" if ok else "degraded", "checks": checks}
        return jsonify(body), (200 if ok else 503)

    return app


def init(app):
    init_logging(app)
    init_health(app)
    init_error_handling(app)
    return app
