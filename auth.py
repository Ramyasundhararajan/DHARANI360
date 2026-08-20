# -*- coding: utf-8 -*-
"""
DHARANI 360 - Authentication
===============================
Lightweight session-based login. Not a hardened multi-tenant auth system -
it is enough to stop a casual open door and to attribute every record to a
real named account instead of free-typed text. See README for the honest
limits of this model.
"""
from functools import wraps
from flask import session, redirect, url_for, request, abort, g
from werkzeug.security import generate_password_hash, check_password_hash

import db
from access import ROLES, depts_for_role, is_admin_role, can_access_dept


def hash_password(pw):
    return generate_password_hash(pw)


def verify_password(pw, pw_hash):
    return check_password_hash(pw_hash, pw)


def current_user():
    if not hasattr(g, "_user"):
        uid = session.get("user_id")
        g._user = db.get_user(uid) if uid else None
    return g._user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        if user.get("must_change_password") and request.endpoint not in ("change_password", "logout"):
            return redirect(url_for("change_password"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login", next=request.path))
        if not is_admin_role(user["role"]):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def dept_access_required(dept_code):
    user = current_user()
    if not user:
        abort(403)
    if not can_access_dept(user["role"], dept_code):
        abort(403)


def allowed_depts_for_current_user():
    user = current_user()
    if not user:
        return []
    return depts_for_role(user["role"])
