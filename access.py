# -*- coding: utf-8 -*-
"""
DHARANI 360 - Roles & access control
=======================================
A small, explicit least-privilege model, matching the access-level design
in the original brief (Receptionist / Agent / Sales Manager / Accountant /
Admin-Operations / IT & Data Management). Add a role by adding one entry
to ROLES. The dictionary KEY is what is stored against each user - only
the label is shown on screen, so a label can be reworded at any time
without touching a single record.
"""

ALL_DEPT_CODES = ["COR", "HR", "AGT", "SAL", "PRO", "TXN", "FIN", "CMP", "IT", "VEN",
                   "PAY", "REC", "ATT", "HLP", "PRJ", "CNT", "MKT"]

ROLES = {
    # Two roles carry full administrative power. They are identical in what
    # they can do and exist only so the screen shows the right title against
    # the right person.
    "CEO": {
        "label": "CEO",
        "depts": ALL_DEPT_CODES,
        "is_admin": True,
        "desc": "Full access to every department, plus Users & Settings.",
    },
    "Director": {
        "label": "IT & Data Management",
        "depts": ALL_DEPT_CODES,
        "is_admin": True,
        "desc": "Full access to every department, plus Users & Settings.",
    },
    "Manager": {
        "label": "Operations Manager",
        "depts": ALL_DEPT_CODES,
        "is_admin": False,
        "desc": "Full access to every department. Cannot manage users or system settings.",
    },
    "Sales Manager": {
        "label": "Sales Manager",
        "depts": ["AGT", "SAL", "PRO", "TXN"],
        "is_admin": False,
        "desc": "Agents, leads/clients, properties and transactions.",
    },
    "Agent": {
        "label": "Agent",
        "depts": ["AGT", "SAL", "PRO"],
        "is_admin": False,
        "desc": "Assigned leads, clients and property information.",
    },
    "Social Media Manager": {
        "label": "Social Media Manager",
        "depts": ["MKT", "CNT"],
        "is_admin": False,
        "desc": "Marketing campaigns, advertising permits, social accounts and published content.",
    },
    "Receptionist": {
        "label": "Receptionist",
        "depts": ["SAL"],
        "is_admin": False,
        "desc": "Client inquiries and lead reception only.",
    },
    "Accountant": {
        "label": "Accountant",
        "depts": ["FIN", "COR", "VEN", "CMP"],
        "is_admin": False,
        "desc": "Finance, tax/corporate documents, vendors and compliance.",
    },
    "Admin / Operations": {
        "label": "Admin / Operations",
        "depts": ["HR", "IT", "VEN", "COR", "CMP", "PAY", "REC", "ATT", "HLP", "PRJ", "CNT"],
        "is_admin": False,
        "desc": "HR, payroll, recruitment, attendance, help desk, assets/IT, vendors, projects, content and compliance.",
    },
}

ROLE_NAMES = list(ROLES.keys())


def depts_for_role(role):
    r = ROLES.get(role)
    return r["depts"] if r else []


def is_admin_role(role):
    r = ROLES.get(role)
    return bool(r and r.get("is_admin"))


def can_access_dept(role, dept_code):
    return dept_code in depts_for_role(role)
