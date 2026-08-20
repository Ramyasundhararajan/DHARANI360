# -*- coding: utf-8 -*-
"""
DHARANI 360 - Icon library
=============================
A small set of hand-built line icons (Feather/Lucide-style: 24x24,
stroke-based, currentColor) plus explicit department -> icon and
form -> icon assignments. Centralised here, separate from forms_data.py,
so the sidebar/nav layer can evolve without touching form definitions.
"""

from markupsafe import Markup

_WRAP = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
         'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
         'stroke-linejoin="round" class="icon">{}</svg>')

_RAW = {
    "board": '<rect x="3" y="3" width="7" height="18" rx="1"/><rect x="14" y="3" width="7" height="18" rx="1"/>',
    "calendar-check": '<rect x="3" y="5" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/><polyline points="9 15 11 17 15 13"/>',
    "search": '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.5" y2="16.5"/>',
    "building": '<rect x="4" y="3" width="16" height="18" rx="1"/><line x1="8" y1="7" x2="8" y2="7.01"/><line x1="12" y1="7" x2="12" y2="7.01"/><line x1="16" y1="7" x2="16" y2="7.01"/><line x1="8" y1="11" x2="8" y2="11.01"/><line x1="12" y1="11" x2="12" y2="11.01"/><line x1="16" y1="11" x2="16" y2="11.01"/><line x1="9" y1="21" x2="9" y2="16" /><line x1="15" y1="21" x2="15" y2="16"/>',
    "shield": '<path d="M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z"/>',
    "file-text": '<path d="M6 2h8l4 4v16H6z"/><path d="M14 2v4h4"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="15" y2="14"/><line x1="9" y1="18" x2="13" y2="18"/>',
    "id-card": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8" cy="11" r="2"/><line x1="6" y1="16" x2="10" y2="16"/><line x1="14" y1="9" x2="18" y2="9"/><line x1="14" y1="13" x2="18" y2="13"/>',
    "home": '<path d="M4 11l8-7 8 7"/><path d="M6 10v10h12V10"/>',
    "key": '<circle cx="8" cy="8" r="4"/><line x1="11" y1="11" x2="20" y2="20"/><line x1="16" y1="16" x2="19" y2="13"/>',
    "handshake": '<path d="M2 12l4.5-3.5 3.5 2.5 3.5-2.5 4.5 3.5"/><path d="M9 11l2.5 2.5-2 2"/><path d="M15 11l-2.5 2.5"/>',
    "git-branch": '<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/><path d="M6 8.2v3a4 4 0 004 4"/><path d="M18 8.2v3a4 4 0 01-4 4"/>',
    "users": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.3"/><path d="M15 20c0-2.4 1.8-4.4 4-4.9"/>',
    "user": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.9 3.1-7 7-7s7 3.1 7 7"/>',
    "user-plus": '<circle cx="10" cy="8" r="3.5"/><path d="M3 20c0-3.9 3.1-7 7-7s7 3.1 7 7"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="16" y1="11" x2="22" y2="11"/>',
    "user-check": '<circle cx="10" cy="8" r="3.5"/><path d="M3 20c0-3.9 3.1-7 7-7s7 3.1 7 7"/><polyline points="17 10 19 12 23 8"/>',
    "user-x": '<circle cx="10" cy="8" r="3.5"/><path d="M3 20c0-3.9 3.1-7 7-7s7 3.1 7 7"/><line x1="17" y1="8" x2="22" y2="13"/><line x1="22" y1="8" x2="17" y2="13"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="8" y1="3" x2="8" y2="7"/><line x1="16" y1="3" x2="16" y2="7"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 16 14"/>',
    "star": '<polygon points="12 2 15 9 22 9.5 17 14.5 18.5 22 12 18 5.5 22 7 14.5 2 9.5 9 9"/>',
    "alert-triangle": '<path d="M12 3l10 18H2z"/><line x1="12" y1="10" x2="12" y2="14.5"/><line x1="12" y1="17" x2="12" y2="17.01"/>',
    "graduation-cap": '<path d="M2 8l10-5 10 5-10 5-10-5z"/><path d="M6 11v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5"/>',
    "repeat": '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 012-2h4a2 2 0 012 2v2"/>',
    "dollar-sign": '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 6.5c0-1.9-2.2-3.5-5-3.5s-5 1.6-5 3.5 2.2 3 5 3.5 5 1.6 5 3.5-2.2 3.5-5 3.5-5-1.6-5-3.5"/>',
    "credit-card": '<rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/>',
    "laptop": '<rect x="4" y="4" width="16" height="10" rx="1"/><line x1="2" y1="18" x2="22" y2="18"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
    "smartphone": '<rect x="7" y="2" width="10" height="20" rx="2"/><line x1="11" y1="18" x2="13" y2="18"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><polyline points="3 6 12 13 21 6"/>',
    "clipboard-list": '<rect x="6" y="3" width="12" height="18" rx="2"/><rect x="9" y="1" width="6" height="4" rx="1"/><line x1="9" y1="10" x2="15" y2="10"/><line x1="9" y1="14" x2="15" y2="14"/><line x1="9" y1="18" x2="13" y2="18"/>',
    "megaphone": '<path d="M3 10v4h4l6 4V6l-6 4z"/><path d="M17 9a4 4 0 010 6"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a15 15 0 010 18 15 15 0 010-18z"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.8"/><polyline points="4 18 9.5 12.5 13 16 16 13.5 20 17.5"/>',
    "hash": '<line x1="9" y1="3" x2="7" y2="21"/><line x1="17" y1="3" x2="15" y2="21"/><line x1="3.5" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="20.5" y2="15"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    # --- record actions: proper, unambiguous verbs -------------------------
    "edit": '<path d="M4 20h4L19 9a2.1 2.1 0 00-3-3L5 17v3z"/><line x1="14.5" y1="6.5" x2="17.5" y2="9.5"/>',
    "trash": '<polyline points="3 6 21 6"/><path d="M8 6V4a1 1 0 011-1h6a1 1 0 011 1v2"/><path d="M6 6l1 14a2 2 0 002 2h6a2 2 0 002-2l1-14"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
    "download": '<path d="M12 3v12"/><polyline points="7 11 12 16 17 11"/><path d="M4 18v1a2 2 0 002 2h12a2 2 0 002-2v-1"/>',
    "share": '<circle cx="18" cy="5" r="2.6"/><circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="19" r="2.6"/><line x1="8.3" y1="10.8" x2="15.7" y2="6.2"/><line x1="8.3" y1="13.2" x2="15.7" y2="17.8"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 01-1-1V4a1 1 0 011-1h10a1 1 0 011 1v1"/>',
    "printer": '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="7" rx="2"/><rect x="7" y="14" width="10" height="7"/>',
    "link": '<path d="M10 13a4 4 0 006 .5l2-2a4 4 0 00-5.7-5.7L11 7"/><path d="M14 11a4 4 0 00-6-.5l-2 2A4 4 0 0011.7 18L13 17"/>',
    "more": '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
    # --- telephony ---------------------------------------------------------
    "phone": '<path d="M4.5 3h3l2 5-2.5 1.5a12 12 0 006 6L15 13l5 2v3a2 2 0 01-2.2 2A17 17 0 013 5.2 2 2 0 014.5 3z"/>',
    "phone-incoming": '<path d="M4.5 9h3l2 5-2.5 1.5a12 12 0 006 6L15 19l5 2v0a2 2 0 01-2.2 2A17 17 0 013 11.2 2 2 0 014.5 9z"/><polyline points="21 3 15 9"/><polyline points="15 4 15 9 20 9"/>',
    "phone-outgoing": '<path d="M4.5 9h3l2 5-2.5 1.5a12 12 0 006 6L15 19l5 2v0a2 2 0 01-2.2 2A17 17 0 013 11.2 2 2 0 014.5 9z"/><polyline points="15 3 21 3 21 9"/><polyline points="15 9 21 3"/>',
    "phone-missed": '<path d="M4.5 9h3l2 5-2.5 1.5a12 12 0 006 6L15 19l5 2v0a2 2 0 01-2.2 2A17 17 0 013 11.2 2 2 0 014.5 9z"/><line x1="15" y1="3" x2="21" y2="9"/><line x1="21" y1="3" x2="15" y2="9"/>',
    "video": '<rect x="2" y="6" width="14" height="12" rx="2"/><path d="M16 10.5l6-3.5v10l-6-3.5z"/>',
    "play": '<polygon points="7 4 20 12 7 20"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7"/><polyline points="3 4 3 9 8 9"/><polyline points="12 8 12 12 15 14"/>',
    "flag": '<line x1="5" y1="2" x2="5" y2="22"/><path d="M5 4h13l-3 4 3 4H5"/>',
    "check-square": '<rect x="3" y="3" width="18" height="18" rx="2"/><polyline points="8 12 11 15 16 9"/>',
    "package": '<path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8"/><line x1="12" y1="13" x2="12" y2="21"/>',
    "archive": '<rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8"/><line x1="10" y1="12" x2="14" y2="12"/>',
    "chevron": '<polyline points="6 9 12 15 18 9"/>',
    "bell": '<path d="M18 15V10a6 6 0 10-12 0v5l-1.6 2.4A.6.6 0 004.9 19h14.2a.6.6 0 00.5-1.6z"/><path d="M10 22a2.2 2.2 0 004 0"/>',
    "bell-off": '<path d="M18 15V10a6 6 0 00-9.3-5"/><path d="M6 9v6l-1.6 2.4A.6.6 0 004.9 19h11"/><path d="M10 22a2.2 2.2 0 004 0"/><line x1="3" y1="3" x2="21" y2="21"/>',
    "chevron-down": '<polyline points="6 9 12 15 18 9"/>',
    "logout": '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    "user-cog": '<circle cx="10" cy="8" r="3.5"/><path d="M3 20c0-3.9 3.1-7 7-7s7 3.1 7 7"/><circle cx="19" cy="16" r="2"/><line x1="19" y1="12.5" x2="19" y2="13.3"/><line x1="19" y1="18.7" x2="19" y2="19.5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.6V21a2 2 0 01-4 0v-.2a1.7 1.7 0 00-1-1.5 1.7 1.7 0 00-1.9.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.6-1H3a2 2 0 010-4h.2a1.7 1.7 0 001.5-1 1.7 1.7 0 00-.3-1.9l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.9.3H9a1.7 1.7 0 001-1.6V3a2 2 0 014 0v.2a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.9V9a1.7 1.7 0 001.6 1H21a2 2 0 010 4h-.2a1.7 1.7 0 00-1.4 1z"/>',
    "help-circle": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.2a2.6 2.6 0 015-1c.6 1.6-.6 2.3-1.6 3-.7.5-1.1 1-1.1 1.9"/><line x1="12" y1="16.7" x2="12" y2="16.71"/>',
    "trending-up": '<polyline points="3 17 9 11 13 15 21 6"/><polyline points="14 6 21 6 21 13"/>',
}


def svg(name, css_class=""):
    raw = _RAW.get(name, _RAW["file-text"])
    tag = _WRAP.format(raw)
    if css_class:
        tag = tag.replace('class="icon"', 'class="icon {}"'.format(css_class))
    return Markup(tag)


DEPT_ICONS = {
    "COR": "building", "HR": "users", "AGT": "id-card", "SAL": "git-branch",
    "PRO": "home", "TXN": "credit-card", "FIN": "dollar-sign", "CMP": "shield",
    "IT": "laptop", "VEN": "package",
    "PAY": "briefcase", "REC": "user-plus", "ATT": "clock", "HLP": "help-circle",
    "PRJ": "flag", "CNT": "megaphone", "MKT": "target",
}

FORM_ICONS = {
    "COR-001": "file-text", "COR-002": "shield", "COR-003": "calendar", "COR-004": "mail", "COR-005": "key",

    "HR-001": "user-plus", "HR-002": "user", "HR-003": "clipboard-list", "HR-004": "check-square",
    "HR-005": "archive", "HR-006": "lock", "HR-007": "calendar", "HR-008": "calendar-check",
    "HR-009": "star", "HR-010": "flag", "HR-011": "alert-triangle", "HR-012": "mail",
    "HR-013": "user-x", "HR-014": "check-square", "HR-015": "lock", "HR-016": "eye", "HR-017": "star",

    "AGT-001": "user-plus", "AGT-002": "id-card", "AGT-003": "handshake", "AGT-004": "flag",
    "AGT-005": "repeat", "AGT-006": "star", "AGT-007": "user-x",

    "SAL-001": "git-branch", "SAL-002": "user", "SAL-003": "home", "SAL-004": "home",
    "SAL-005": "eye", "SAL-006": "clock", "SAL-007": "handshake", "SAL-008": "repeat",

    "PRO-001": "home", "PRO-002": "user-check", "PRO-003": "key", "PRO-004": "clipboard-list",
    "PRO-005": "megaphone", "PRO-006": "check-square", "PRO-007": "archive",

    "TXN-001": "clipboard-list", "TXN-002": "file-text", "TXN-003": "dollar-sign",
    "TXN-004": "check-square", "TXN-005": "lock", "TXN-006": "handshake",

    "FIN-001": "credit-card", "FIN-002": "file-text", "FIN-003": "clipboard-list",
    "FIN-004": "check-square", "FIN-005": "dollar-sign", "FIN-006": "file-text",
    "FIN-007": "lock", "FIN-008": "clipboard-list",

    "CMP-001": "user-check", "CMP-002": "shield", "CMP-003": "dollar-sign", "CMP-004": "id-card",
    "CMP-005": "alert-triangle", "CMP-006": "flag", "CMP-007": "graduation-cap",

    "IT-001": "archive", "IT-002": "archive", "IT-003": "key", "IT-004": "smartphone",
    "IT-005": "lock", "IT-006": "lock", "IT-007": "archive", "IT-008": "alert-triangle",

    "VEN-001": "package", "VEN-002": "user-check", "VEN-003": "file-text", "VEN-004": "star",

    "PAY-001": "clipboard-list", "PAY-002": "dollar-sign", "PAY-003": "credit-card",

    "REC-001": "clipboard-list", "REC-002": "users", "REC-003": "check-square",

    "ATT-001": "calendar-check", "ATT-002": "clock",

    "HLP-001": "help-circle", "HLP-002": "clipboard-list",

    "PRJ-001": "flag", "PRJ-002": "check-square",
    "CNT-001": "file-text", "CNT-002": "megaphone",

    "MKT-001": "target",        "MKT-002": "flag",          "MKT-003": "dollar-sign",
    "MKT-004": "edit",          "MKT-005": "check-square",  "MKT-006": "calendar",
    "MKT-007": "globe",         "MKT-008": "credit-card",   "MKT-009": "git-branch",
    "MKT-010": "handshake",     "MKT-011": "trending-up",   "MKT-012": "board",
    "MKT-013": "laptop",        "MKT-014": "lock",          "MKT-015": "package",
    "MKT-016": "file-text",     "MKT-017": "megaphone",     "MKT-018": "printer",
    "MKT-019": "image",         "MKT-020": "archive",
}

DASHBOARD_ICONS = {
    "admin": "board", "employee": "users", "deals": "credit-card", "leads": "git-branch",
    "hr": "users", "payroll": "briefcase", "recruitment": "user-plus", "attendance": "clock",
    "finance": "dollar-sign", "it-admin": "lock", "asset": "archive", "helpdesk": "help-circle",
    "marketing": "target",
}


def dashboard_icon(key):
    return svg(DASHBOARD_ICONS.get(key, "trending-up"))


def dept_icon(dept_code):
    return svg(DEPT_ICONS.get(dept_code, "building"))


def form_icon(form_code):
    return svg(FORM_ICONS.get(form_code, "file-text"))
