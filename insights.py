# -*- coding: utf-8 -*-
"""
DHARANI 360 - Department Insights Engine
==========================================
This is where "the register becomes the memory of the company" turns into
something a department head can actually read at a glance. Each department
gets its own panels — a KPI row, a pipeline/funnel where the business has a
real workflow, a breakdown chart where a field categorises the work, and a
short worklist of what needs attention right now.

Every panel is built from real queries against the SQLite registers (via
db.py) using the exact field names defined in forms_data.py — nothing here
is decorative or hardcoded to demo data. With zero records every panel
still renders correctly (empty states), and as records are entered the
picture fills in on its own.

Panel shapes consumed by templates/department.html:
  {"type": "kpis", "kpis": [{"label", "value", "tone"}]}
  {"type": "funnel", "title", "stages": [{"label", "count"}]}
  {"type": "breakdown", "title", "form_code", "field_label", "bars": [{"label","count","pct"}]}
  {"type": "list", "title", "icon", "empty_text", "rows": [{"form_code","record_id","doc_no",
                                                             "title","meta","tone"}]}
"""
from datetime import date

import db


def _pct(n, total):
    if not total:
        return 0
    return round(100 * n / total)


def _bars_from_counts(counts, total=None, color_fn=None):
    total = total if total is not None else sum(c["count"] for c in counts)
    bars = [{"label": c["value"], "count": c["count"], "pct": _pct(c["count"], total)} for c in counts]
    if color_fn:
        for b in bars:
            b["color"] = color_fn(b["label"])
    return bars


_RISK_COLORS = {"low risk": "var(--green)", "medium risk": "var(--amber)", "high risk": "var(--red)"}


def _risk_color(label):
    return _RISK_COLORS.get(str(label).strip().lower(), "var(--accent)")


def _kpi(label, value, tone="neutral"):
    return {"label": label, "value": value, "tone": tone}


# ============================================================================
# Corporate & Licensing
# ============================================================================

def _cor():
    panels = []
    docs = db.count_records("COR-001")
    licences_valid = db.count_where_in("COR-002", "status", ["Valid"])
    licences_total = db.count_records("COR-002")
    compliance_open = db.count_where_in("COR-003", "status", ["Not Started", "In Progress", "Overdue"])
    correspondence_open = db.count_where_in("COR-004", "status", ["Open", "Awaiting Response"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Corporate documents on file", docs, "blue"),
        _kpi("Licences valid", "{}/{}".format(licences_valid, licences_total), "green" if licences_valid == licences_total and licences_total else "amber"),
        _kpi("Compliance items open", compliance_open, "red" if compliance_open else "green"),
        _kpi("Correspondence awaiting reply", correspondence_open, "amber" if correspondence_open else "green"),
    ]})

    calendar_due = db.records_upcoming("COR-003", "due_date", days_ahead=30, limit=8)
    panels.append({"type": "list", "title": "Compliance Calendar — Due Within 30 Days", "icon": "calendar-check",
                    "empty_text": "Nothing due on the compliance calendar in the next 30 days.",
                    "rows": [{"form_code": "COR-003", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("compliance_item") or r["doc_no"],
                               "meta": "{} · due {} ({}d)".format(r.get("authority") or "—", r.get("due_date") or "—",
                                                                    r["_days"]),
                               "tone": "RED" if r["_days"] <= 7 else "AMBER"} for r in calendar_due]})

    licence_bars = db.field_counts("COR-002", "licence_permit")
    if licence_bars:
        panels.append({"type": "breakdown", "title": "Licences & Permits on File", "bars": _bars_from_counts(licence_bars)})
    return panels


# ============================================================================
# People & HR
# ============================================================================

def _hr():
    panels = []
    active = db.count_where_in("HR-002", "status", ["Active"])
    on_leave = db.count_where_in("HR-002", "status", ["On Leave"])
    onboarding = db.count_where_in("HR-001", "status", ["In Progress"])
    leave_pending = db.count_where_in("HR-007", "status", ["Pending"])
    grievances_open = db.count_where_in("HR-012", "status", ["Open", "Under Investigation"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Active headcount", active, "green"),
        _kpi("On leave right now", on_leave, "blue"),
        _kpi("Onboarding in progress", onboarding, "amber" if onboarding else "neutral"),
        _kpi("Leave requests pending", leave_pending, "amber" if leave_pending else "green"),
        _kpi("Open grievances", grievances_open, "red" if grievances_open else "green"),
    ]})

    exiting = db.count_where_in("HR-013", "status", ["In Progress"])
    exited = db.count_where_in("HR-002", "status", ["Exited"])
    panels.append({"type": "funnel", "title": "Employee Lifecycle", "stages": [
        {"label": "Onboarding", "count": onboarding},
        {"label": "Active", "count": active},
        {"label": "On Leave", "count": on_leave},
        {"label": "Exit in Progress", "count": exiting},
        {"label": "Exited", "count": exited},
    ]})

    leave_rows = db.records_where_in("HR-007", "status", ["Pending"], limit=8, order_by="from_date ASC")
    panels.append({"type": "list", "title": "Leave Requests Awaiting Approval", "icon": "calendar",
                    "empty_text": "No leave requests waiting on approval.",
                    "rows": [{"form_code": "HR-007", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("employee_name") or r["doc_no"],
                               "meta": "{} · {} → {}".format(r.get("leave_type") or "Leave", r.get("from_date") or "—", r.get("to_date") or "—"),
                               "tone": "AMBER"} for r in leave_rows]})

    warnings = db.records_where_in("HR-011", "status", ["Issued", "Escalated"], limit=6)
    if warnings or grievances_open:
        rows = [{"form_code": "HR-011", "record_id": r["id"], "doc_no": r["doc_no"],
                  "title": r.get("employee_name") or r["doc_no"],
                  "meta": "{} warning · {}".format(r.get("warning_level") or "—", r.get("incident_date") or "—"),
                  "tone": "RED"} for r in warnings]
        panels.append({"type": "list", "title": "Discipline & Grievances Needing Attention", "icon": "alert-triangle",
                        "empty_text": "No open disciplinary or grievance items.", "rows": rows})
    return panels


# ============================================================================
# Agents & Brokers
# ============================================================================

def _agt():
    panels = []
    active_agents = db.count_where_in("AGT-002", "status", ["Active"])
    total_agents = db.count_records("AGT-002")
    disputed_leads = db.count_where_in("AGT-004", "status", ["Disputed"])
    onboarding = db.count_where_in("AGT-001", "status", ["In Progress"])
    signed_agreements = db.count_where_in("AGT-003", "status", ["Signed"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Active agents", "{}/{}".format(active_agents, total_agents), "green"),
        _kpi("Onboarding in progress", onboarding, "amber" if onboarding else "neutral"),
        _kpi("Commission agreements signed", signed_agreements, "blue"),
        _kpi("Lead ownership disputes", disputed_leads, "red" if disputed_leads else "green"),
    ]})

    disputes = db.records_where_in("AGT-004", "status", ["Disputed"], limit=8)
    panels.append({"type": "list", "title": "Lead Ownership Disputes", "icon": "flag",
                    "empty_text": "No lead ownership disputes open.",
                    "rows": [{"form_code": "AGT-004", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("client_name") or r.get("lead_id") or r["doc_no"],
                               "meta": "claimed by {}".format(r.get("agent_name") or "—"),
                               "tone": "RED"} for r in disputes]})

    reviews = db.get_records("AGT-006", page=None)[0]
    leaderboard = sorted(
        [r for r in reviews if (r.get("deals_closed") or 0)],
        key=lambda r: (r.get("deals_closed") or 0, r.get("revenue_generated") or 0), reverse=True
    )[:6]
    if leaderboard:
        total_deals = sum((r.get("deals_closed") or 0) for r in leaderboard) or 1
        panels.append({"type": "breakdown", "title": "Agent Performance — Deals Closed (latest reviews)",
                        "bars": [{"label": r.get("agent_name") or r["doc_no"],
                                   "count": int(r.get("deals_closed") or 0),
                                   "pct": _pct(r.get("deals_closed") or 0, total_deals)} for r in leaderboard]})
    return panels


# ============================================================================
# Sales, Leads & Clients
# ============================================================================

def _sal():
    panels = []
    leads_total = db.count_records("SAL-001")
    qualified = db.count_where_in("SAL-001", "status", ["Qualified"])
    converted = db.count_where_in("SAL-001", "status", ["Converted"])
    active_clients = db.count_where_in("SAL-002", "status", ["Active"])
    viewings = db.count_records("SAL-005")
    offers_pending = db.count_where_in("SAL-007", "status", ["Pending"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Total leads", leads_total, "blue"),
        _kpi("Active clients", active_clients, "green"),
        _kpi("Viewings logged", viewings, "blue"),
        _kpi("Offers pending", offers_pending, "amber" if offers_pending else "neutral"),
        _kpi("Leads converted", converted, "green"),
    ]})

    panels.append({"type": "funnel", "title": "Sales Pipeline", "stages": [
        {"label": "Leads", "count": leads_total},
        {"label": "Qualified", "count": qualified},
        {"label": "Viewings", "count": viewings},
        {"label": "Offers", "count": db.count_records("SAL-007")},
        {"label": "Converted", "count": converted},
    ]})

    followups = db.records_upcoming("SAL-006", "next_follow_up", days_ahead=7, limit=8)
    followups = [r for r in followups if (r.get("status") or "").lower() != "completed"]
    panels.append({"type": "list", "title": "Follow-ups Due Within 7 Days", "icon": "clock",
                    "empty_text": "No follow-ups due — nothing buried in WhatsApp right now.",
                    "rows": [{"form_code": "SAL-006", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("client_name") or r["doc_no"],
                               "meta": "with {} · due {} ({}d)".format(r.get("agent") or "—",
                                                                          r.get("next_follow_up") or "—", r["_days"]),
                               "tone": "RED" if r["_days"] < 0 else "AMBER"} for r in followups]})

    source_bars = db.field_counts("SAL-001", "source")
    if source_bars:
        panels.append({"type": "breakdown", "title": "Lead Source Mix", "bars": _bars_from_counts(source_bars)})
    return panels


# ============================================================================
# Properties & Owners
# ============================================================================

def _pro():
    panels = []
    active_props = db.count_where_in("PRO-001", "status", ["Active"])
    total_props = db.count_records("PRO-001")
    kyc_pending = db.count_where_in("PRO-002", "status", ["Pending"])
    listings_active = db.count_where_in("PRO-005", "status", ["Active"])
    ads_pending = db.count_where_in("PRO-006", "status", ["Pending"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Properties on file", total_props, "blue"),
        _kpi("Active listings", active_props, "green"),
        _kpi("Owner KYC pending", kyc_pending, "amber" if kyc_pending else "green"),
        _kpi("Marketing authorizations active", listings_active, "blue"),
        _kpi("Ads awaiting approval", ads_pending, "amber" if ads_pending else "neutral"),
    ]})

    status_bars = db.field_counts("PRO-001", "status")
    if status_bars:
        panels.append({"type": "breakdown", "title": "Property Portfolio by Status", "bars": _bars_from_counts(status_bars)})

    auth_due = db.records_upcoming("PRO-003", "valid_to", days_ahead=90, limit=8)
    panels.append({"type": "list", "title": "Owner Authorizations Expiring Within 90 Days", "icon": "id-card",
                    "empty_text": "No owner authorizations expiring soon.",
                    "rows": [{"form_code": "PRO-003", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("owner_name") or r["doc_no"],
                               "meta": "{} · expires {} ({}d)".format(r.get("property_ref") or "—", r.get("valid_to") or "—", r["_days"]),
                               "tone": "RED" if r["_days"] <= 30 else "AMBER"} for r in auth_due]})
    return panels


# ============================================================================
# Transactions & Commissions
# ============================================================================

def _txn():
    panels = []
    opened = db.count_where_in("TXN-001", "status", ["Open"])
    total_txn = db.count_records("TXN-001")
    docs_complete = db.count_where_in("TXN-002", "status", ["Complete"])
    approvals_pending = db.count_where_in("TXN-004", "status", ["Pending"])
    closed = db.count_where_in("TXN-005", "status", ["Closed", "Archived"])
    commission_paid = db.sum_field("TXN-004", "net_commission", "status", ["Paid"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Open transactions", opened, "blue"),
        _kpi("Docs complete", docs_complete, "green"),
        _kpi("Commission approvals pending", approvals_pending, "red" if approvals_pending else "green"),
        _kpi("Closed transactions", closed, "green"),
        _kpi("Commission paid (AED)", "{:,.0f}".format(commission_paid), "blue"),
    ]})

    panels.append({"type": "funnel", "title": "Transaction Pipeline", "stages": [
        {"label": "Opened", "count": total_txn},
        {"label": "Docs Complete", "count": docs_complete},
        {"label": "Commission Calculated", "count": db.count_records("TXN-003")},
        {"label": "Approved / Paid", "count": db.count_where_in("TXN-004", "status", ["Approved", "Paid"])},
        {"label": "Closed", "count": closed},
    ]})

    queue = db.records_where_in("TXN-004", "status", ["Pending", "Finance Verified"], limit=8)
    panels.append({"type": "list", "title": "Commission Approval Queue", "icon": "dollar-sign",
                    "empty_text": "No commission approvals waiting.",
                    "rows": [{"form_code": "TXN-004", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("agent_name") or r["doc_no"],
                               "meta": "{} · net AED {:,.0f}".format(r.get("transaction_ref") or "—", r.get("net_commission") or 0),
                               "tone": "AMBER"} for r in queue]})
    return panels


# ============================================================================
# Finance & Accounting
# ============================================================================

def _fin():
    panels = []
    payments_pending = db.count_where_in("FIN-004", "status", ["Pending", "Verified"])
    expenses_pending = db.count_where_in("FIN-001", "status", ["Pending"])
    po_open = db.count_where_in("FIN-003", "status", ["Issued"])
    invoices_pending = db.count_where_in("FIN-006", "status", ["Pending"])
    petty_balance = db.latest_value("FIN-005", "balance", order_by="id DESC")

    panels.append({"type": "kpis", "kpis": [
        _kpi("Payment approvals pending", payments_pending, "red" if payments_pending else "green"),
        _kpi("Expense claims pending", expenses_pending, "amber" if expenses_pending else "green"),
        _kpi("Purchase orders open", po_open, "blue"),
        _kpi("Vendor invoices pending verification", invoices_pending, "amber" if invoices_pending else "green"),
        _kpi("Petty cash balance (AED)", "{:,.0f}".format(float(petty_balance)) if petty_balance not in (None, "") else "—", "blue"),
    ]})

    queue_rows = []
    for r in db.records_where_in("FIN-004", "status", ["Pending", "Verified"], limit=5):
        queue_rows.append({"form_code": "FIN-004", "record_id": r["id"], "doc_no": r["doc_no"],
                             "title": r.get("payee_name") or r["doc_no"],
                             "meta": "Payment · AED {:,.0f}".format(r.get("amount") or 0), "tone": "RED"})
    for r in db.records_where_in("FIN-001", "status", ["Pending"], limit=5):
        queue_rows.append({"form_code": "FIN-001", "record_id": r["id"], "doc_no": r["doc_no"],
                             "title": r.get("employee_name") or r["doc_no"],
                             "meta": "Expense claim · AED {:,.0f}".format(r.get("amount") or 0), "tone": "AMBER"})
    panels.append({"type": "list", "title": "Approval Queue", "icon": "credit-card",
                    "empty_text": "Nothing waiting for financial approval.", "rows": queue_rows[:8]})
    return panels


# ============================================================================
# AML, KYC & Compliance
# ============================================================================

def _cmp():
    panels = []
    kyc_complete = db.count_where_in("CMP-001", "status", ["Complete"])
    kyc_total = db.count_records("CMP-001")
    escalations_open = db.count_where_in("CMP-006", "status", ["Escalated"])
    incidents_open = db.count_where_in("CMP-005", "status", ["Open", "Investigating"])
    training_total = db.count_records("CMP-007")
    training_done = db.count_where_in("CMP-007", "status", ["Completed"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("KYC checklists complete", "{}/{}".format(kyc_complete, kyc_total), "green" if kyc_total and kyc_complete == kyc_total else "amber"),
        _kpi("Suspicious activity escalations open", escalations_open, "red" if escalations_open else "green"),
        _kpi("Compliance incidents open", incidents_open, "red" if incidents_open else "green"),
        _kpi("Staff training completed", "{}/{}".format(training_done, training_total), "blue"),
    ]})

    risk_bars = db.field_counts("CMP-002", "risk_rating")
    if risk_bars:
        panels.append({"type": "breakdown", "title": "AML Risk Distribution",
                        "bars": _bars_from_counts(risk_bars, color_fn=_risk_color)})

    open_items = db.records_where_in("CMP-006", "status", ["Escalated"], limit=5)
    incident_items = db.records_where_in("CMP-005", "status", ["Open", "Investigating"], limit=5)
    rows = [{"form_code": "CMP-006", "record_id": r["id"], "doc_no": r["doc_no"],
              "title": r.get("client_name") or r["doc_no"],
              "meta": "Escalated to {} · {}".format(r.get("escalated_to") or "—", r.get("date") or "—"),
              "tone": "RED"} for r in open_items]
    rows += [{"form_code": "CMP-005", "record_id": r["id"], "doc_no": r["doc_no"],
               "title": r.get("description") and r["description"][:50] or r["doc_no"],
               "meta": "Incident · {}".format(r.get("incident_date") or "—"), "tone": "RED"} for r in incident_items]
    panels.append({"type": "list", "title": "Open Escalations & Incidents", "icon": "shield",
                    "empty_text": "No open AML escalations or compliance incidents.", "rows": rows[:8]})
    return panels


# ============================================================================
# Assets, IT & Security
# ============================================================================

def _it():
    panels = []
    total_assets = db.count_records("IT-001")
    in_use = db.count_where_in("IT-001", "status", ["In Use"])
    incidents_open = db.count_where_in("IT-008", "status", ["Open", "Investigating"])
    admin_review = db.count_where_in("IT-006", "status", ["Needs Review"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Total assets on register", total_assets, "blue"),
        _kpi("Assets in use", in_use, "green"),
        _kpi("Open security incidents", incidents_open, "red" if incidents_open else "green"),
        _kpi("Admin accounts needing review", admin_review, "amber" if admin_review else "green"),
    ]})

    type_bars = db.field_counts("IT-001", "asset_type")
    if type_bars:
        panels.append({"type": "breakdown", "title": "Asset Register by Type", "bars": _bars_from_counts(type_bars)})

    incidents = db.records_where_in("IT-008", "status", ["Open", "Investigating"], limit=8)
    panels.append({"type": "list", "title": "Open Security Incidents", "icon": "alert-triangle",
                    "empty_text": "No open security incidents.",
                    "rows": [{"form_code": "IT-008", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("incident_type") or r["doc_no"],
                               "meta": "reported by {} · {}".format(r.get("reported_by") or "—", r.get("incident_date") or "—"),
                               "tone": "RED"} for r in incidents]})
    return panels


# ============================================================================
# Vendors & Administration
# ============================================================================

def _ven():
    panels = []
    active_vendors = db.count_where_in("VEN-001", "status", ["Active", "Onboarded"])
    total_vendors = db.count_records("VEN-001")
    dd_pending = db.count_where_in("VEN-002", "status", ["Pending"])
    contracts_expiring = db.count_where_in("VEN-003", "status", ["Expiring Soon"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Active vendors", "{}/{}".format(active_vendors, total_vendors), "green"),
        _kpi("Due diligence pending", dd_pending, "amber" if dd_pending else "green"),
        _kpi("Contracts expiring soon", contracts_expiring, "amber" if contracts_expiring else "green"),
    ]})

    status_bars = db.field_counts("VEN-003", "status")
    if status_bars:
        panels.append({"type": "breakdown", "title": "Vendor Contracts by Status", "bars": _bars_from_counts(status_bars)})

    dd_rows = db.records_where_in("VEN-002", "status", ["Pending"], limit=8)
    panels.append({"type": "list", "title": "Vendor Due Diligence Pending", "icon": "briefcase",
                    "empty_text": "No vendor due-diligence checks pending.",
                    "rows": [{"form_code": "VEN-002", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("vendor_name") or r["doc_no"],
                               "meta": "requested {}".format(r.get("date") or "—"), "tone": "AMBER"} for r in dd_rows]})
    return panels


# ============================================================================
# Payroll
# ============================================================================

def _pay():
    panels = []
    runs_processed = db.count_where_in("PAY-001", "status", ["Processed", "Paid"])
    latest_net = db.latest_value("PAY-001", "net_total", order_by="id DESC")
    structures = db.count_records("PAY-002")
    advances_pending = db.count_where_in("PAY-003", "status", ["Pending"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Payroll runs processed", runs_processed, "green"),
        _kpi("Latest run net total (AED)", "{:,.0f}".format(float(latest_net)) if latest_net not in (None, "") else "—", "blue"),
        _kpi("Salary structures on file", structures, "blue"),
        _kpi("Salary advances pending", advances_pending, "amber" if advances_pending else "green"),
    ]})

    dept_bars = db.field_counts("PAY-002", "department")
    if dept_bars:
        panels.append({"type": "breakdown", "title": "Salary Structures by Department", "bars": _bars_from_counts(dept_bars)})

    advance_rows = db.records_where_in("PAY-003", "status", ["Pending"], limit=8)
    panels.append({"type": "list", "title": "Salary Advances Awaiting Approval", "icon": "credit-card",
                    "empty_text": "No salary advance/loan requests pending.",
                    "rows": [{"form_code": "PAY-003", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("employee_name") or r["doc_no"],
                               "meta": "AED {:,.0f} · requested {}".format(r.get("amount") or 0, r.get("requested_date") or "—"),
                               "tone": "AMBER"} for r in advance_rows]})
    return panels


# ============================================================================
# Recruitment
# ============================================================================

def _rec():
    panels = []
    open_reqs = db.count_where_in("REC-001", "status", ["Open"])
    pipeline_total = db.count_records("REC-002")
    interviews = db.count_where_in("REC-002", "status", ["Interview"])
    offers_pending = db.count_where_in("REC-003", "status", ["Pending"])
    hired = db.count_where_in("REC-002", "status", ["Hired"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Open requisitions", open_reqs, "amber" if open_reqs else "green"),
        _kpi("Candidates in pipeline", pipeline_total, "blue"),
        _kpi("Interviews scheduled", interviews, "blue"),
        _kpi("Offers pending", offers_pending, "amber" if offers_pending else "neutral"),
        _kpi("Hired (all time)", hired, "green"),
    ]})

    panels.append({"type": "funnel", "title": "Candidate Pipeline", "stages": [
        {"label": "Applied", "count": db.count_where_in("REC-002", "status", ["Applied"])},
        {"label": "Screening", "count": db.count_where_in("REC-002", "status", ["Screening"])},
        {"label": "Interview", "count": interviews},
        {"label": "Offer", "count": db.count_where_in("REC-002", "status", ["Offer"])},
        {"label": "Hired", "count": hired},
    ]})

    req_rows = db.records_where_in("REC-001", "status", ["Open"], limit=8)
    panels.append({"type": "list", "title": "Open Requisitions", "icon": "briefcase",
                    "empty_text": "No open job requisitions.",
                    "rows": [{"form_code": "REC-001", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("position_title") or r["doc_no"],
                               "meta": "{} opening(s) · {} · {} priority".format(
                                   int(r.get("no_of_openings") or 0), r.get("department") or "—", r.get("priority") or "—"),
                               "tone": "AMBER" if (r.get("priority") or "").lower() in ("high", "urgent") else "BLUE"} for r in req_rows]})

    source_bars = db.field_counts("REC-002", "source")
    if source_bars:
        panels.append({"type": "breakdown", "title": "Candidate Source Mix", "bars": _bars_from_counts(source_bars)})
    return panels


# ============================================================================
# Attendance
# ============================================================================

def _att():
    panels = []
    today = date.today().isoformat()
    first_of_month = date.today().replace(day=1).isoformat()

    present = db.count_where("ATT-001", [("date", "eq", today), ("status", "in", ["Present"])])
    absent = db.count_where("ATT-001", [("date", "eq", today), ("status", "in", ["Absent"])])
    late = db.count_where("ATT-001", [("date", "eq", today), ("status", "in", ["Late"])])
    on_leave = db.count_where("ATT-001", [("date", "eq", today), ("status", "in", ["On Leave"])])
    half_day = db.count_where("ATT-001", [("date", "eq", today), ("status", "in", ["Half Day"])])
    overtime_pending = db.count_where_in("ATT-002", "status", ["Requested"])

    present_month = db.count_where("ATT-001", [("date", "gte", first_of_month), ("status", "in", ["Present"])])
    logged_month = db.count_where("ATT-001", [("date", "gte", first_of_month)])
    rate = _pct(present_month, logged_month) if logged_month else None

    panels.append({"type": "kpis", "kpis": [
        _kpi("Present today", present, "green"),
        _kpi("Absent today", absent, "red" if absent else "green"),
        _kpi("Late today", late, "amber" if late else "green"),
        _kpi("On leave today", on_leave, "blue"),
        _kpi("Attendance rate this month", "{}%".format(rate) if rate is not None else "—", "blue"),
        _kpi("Overtime requests pending", overtime_pending, "amber" if overtime_pending else "green"),
    ]})

    today_total = present + absent + late + on_leave + half_day
    if today_total:
        mix = [
            {"value": "Present", "count": present}, {"value": "Absent", "count": absent},
            {"value": "Late", "count": late}, {"value": "Half Day", "count": half_day},
            {"value": "On Leave", "count": on_leave},
        ]
        mix = [m for m in mix if m["count"]]
        panels.append({"type": "breakdown", "title": "Today's Attendance Mix",
                        "bars": _bars_from_counts(mix, total=today_total)})

    ot_rows = db.records_where_in("ATT-002", "status", ["Requested"], limit=8)
    panels.append({"type": "list", "title": "Overtime Requests Pending", "icon": "clock",
                    "empty_text": "No overtime requests pending.",
                    "rows": [{"form_code": "ATT-002", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("employee_name") or r["doc_no"],
                               "meta": "{}h · {}".format(r.get("hours") or 0, r.get("date") or "—"),
                               "tone": "AMBER"} for r in ot_rows]})
    return panels


# ============================================================================
# Help Desk
# ============================================================================

def _hlp():
    panels = []
    first_of_month = date.today().replace(day=1).isoformat()

    open_tickets = db.count_where_in("HLP-001", "status", ["Open", "In Progress"])
    critical_open = db.count_where("HLP-001", [("status", "in", ["Open", "In Progress"]), ("priority", "in", ["High", "Critical"])])
    resolved_month = db.count_where("HLP-001", [("status", "in", ["Resolved", "Closed"]), ("date_resolved", "gte", first_of_month)])
    requests_pending = db.count_where_in("HLP-002", "status", ["Pending"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Open tickets", open_tickets, "amber" if open_tickets else "green"),
        _kpi("High/Critical priority open", critical_open, "red" if critical_open else "green"),
        _kpi("Resolved this month", resolved_month, "green"),
        _kpi("General requests pending", requests_pending, "amber" if requests_pending else "green"),
    ]})

    cat_bars = db.field_counts("HLP-001", "category")
    if cat_bars:
        panels.append({"type": "breakdown", "title": "Tickets by Category", "bars": _bars_from_counts(cat_bars)})

    def _ticket_tone(priority):
        p = (priority or "").lower()
        if p in ("high", "critical"):
            return "RED"
        if p == "medium":
            return "AMBER"
        return "BLUE"

    ticket_rows = db.records_where_in("HLP-001", "status", ["Open", "In Progress"], limit=8)
    panels.append({"type": "list", "title": "Open Tickets", "icon": "help-circle",
                    "empty_text": "No open support tickets.",
                    "rows": [{"form_code": "HLP-001", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("subject") or r["doc_no"],
                               "meta": "{} · {} priority · raised by {}".format(
                                   r.get("category") or "—", r.get("priority") or "—", r.get("raised_by") or "—"),
                               "tone": _ticket_tone(r.get("priority"))} for r in ticket_rows]})
    return panels


# ============================================================================
# Marketing
# ============================================================================

def _mkt():
    panels = []
    live_campaigns = db.count_where_in("MKT-001", "status", ["Live", "Approved"])
    total_campaigns = db.count_records("MKT-001")
    awaiting_approval = db.count_where_in("MKT-005", "status", ["Submitted"])
    budget_pending = db.count_where_in("MKT-003", "status", ["Submitted"])
    approved_budget = db.sum_field("MKT-003", "approved_amount_aed")
    ad_spend = db.sum_field("MKT-008", "spend_to_date_aed")
    leads_handed = db.count_records("MKT-010")
    leads_accepted = db.count_where_in("MKT-010", "status", ["Accepted"])

    # Permits are the department's single biggest exposure: AED 50,000 a time.
    permits_expiring = db.records_upcoming("MKT-005", "permit_expiry", days_ahead=30, limit=1000)

    panels.append({"type": "kpis", "kpis": [
        _kpi("Live campaigns", "{}/{}".format(live_campaigns, total_campaigns), "green"),
        _kpi("Permits expiring ≤ 30 days", len(permits_expiring), "red" if permits_expiring else "green"),
        _kpi("Content awaiting approval", awaiting_approval, "amber" if awaiting_approval else "green"),
        _kpi("Budgets awaiting approval", budget_pending, "amber" if budget_pending else "green"),
        _kpi("Approved budget (AED)", "{:,.0f}".format(float(approved_budget or 0)), "blue"),
        _kpi("Ad spend to date (AED)", "{:,.0f}".format(float(ad_spend or 0)), "blue"),
        _kpi("Leads handed to Sales", "{}/{} accepted".format(leads_accepted, leads_handed), "green"),
    ]})

    channel_bars = db.field_counts("MKT-001", "primary_channel")
    if channel_bars:
        panels.append({"type": "breakdown", "title": "Campaigns by Channel", "bars": _bars_from_counts(channel_bars)})

    platform_bars = db.field_counts("MKT-007", "platform")
    if platform_bars:
        panels.append({"type": "breakdown", "title": "Paid Advertising by Platform", "bars": _bars_from_counts(platform_bars)})

    consent_bars = db.field_counts("MKT-010", "consent_basis")
    if consent_bars:
        panels.append({"type": "breakdown", "title": "Lead Consent Basis", "bars": _bars_from_counts(consent_bars)})

    panels.append({"type": "list", "title": "Advertising Permits Expiring Within 30 Days", "icon": "alert-triangle",
                    "empty_text": "No advertising permits expiring in the next 30 days.",
                    "rows": [{"form_code": "MKT-005", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("content_title") or r["doc_no"],
                               "meta": "permit {} · expires {} ({}d)".format(
                                   r.get("trakheesi_permit_no") or "—", r.get("permit_expiry") or "—", r["_days"]),
                               "tone": "RED" if r["_days"] <= 7 else "AMBER"} for r in permits_expiring[:8]]})

    pending_content = db.records_where_in("MKT-005", "status", ["Submitted"], limit=8)
    panels.append({"type": "list", "title": "Content Awaiting Approval", "icon": "check-square",
                    "empty_text": "Nothing waiting on a content approval.",
                    "rows": [{"form_code": "MKT-005", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("content_title") or r["doc_no"],
                               "meta": "{} · submitted by {}".format(
                                   r.get("content_type") or "—", r.get("submitted_by") or "—"),
                               "tone": "AMBER"} for r in pending_content]})

    upcoming_posts = db.records_upcoming("MKT-006", "scheduled_date", days_ahead=14,
                                          include_overdue=False, limit=8)
    panels.append({"type": "list", "title": "Scheduled Posts — Next 14 Days", "icon": "calendar",
                    "empty_text": "Nothing scheduled in the next fortnight.",
                    "rows": [{"form_code": "MKT-006", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("post_title") or r["doc_no"],
                               "meta": "{} · {} ({}d)".format(
                                   r.get("platform") or "—", r.get("scheduled_date") or "—", r["_days"]),
                               "tone": "BLUE"} for r in upcoming_posts]})

    access_review = db.records_upcoming("MKT-014", "review_due_date", days_ahead=30, limit=8)
    panels.append({"type": "list", "title": "Account Access Due for Review", "icon": "lock",
                    "empty_text": "No social or ad account access due for review.",
                    "rows": [{"form_code": "MKT-014", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": "{} — {}".format(r.get("platform") or "—", r.get("person_name") or "—"),
                               "meta": "{} access · review {} ({}d)".format(
                                   r.get("access_level") or "—", r.get("review_due_date") or "—", r["_days"]),
                               "tone": "RED" if r["_days"] <= 0 else "AMBER"} for r in access_review]})
    return panels


BUILDERS = {
    "COR": _cor, "HR": _hr, "AGT": _agt, "SAL": _sal, "PRO": _pro,
    "TXN": _txn, "FIN": _fin, "CMP": _cmp, "IT": _it, "VEN": _ven,
    "PAY": _pay, "REC": _rec, "ATT": _att, "HLP": _hlp, "MKT": _mkt,
}


def build(dept_code):
    fn = BUILDERS.get(dept_code)
    if not fn:
        return []
    try:
        return fn()
    except Exception:
        # An insights panel should never take the whole department page down.
        return []


# ============================================================================
# Dashboards — the "Dashboard" sidebar group
# ----------------------------------------------------------------------------
# 12 named dashboards. Most are a straight read of one department's full
# insight panel set (builder "dept"); three are bespoke cross-cutting or
# focused views built below (employee, it-admin, asset) so that e.g. "IT
# Admin Dashboard" (systems/security) and "Asset Dashboard" (the physical
# register) — both backed by the same IT department — show different
# panels rather than duplicating each other.
# ============================================================================

DASHBOARDS = [
    {"key": "admin", "title": "Admin Dashboard", "dept": None, "tag": None,
     "desc": "Company-wide control tower — every department, every red/amber item, in one view."},
    {"key": "employee", "title": "Employee Dashboard", "dept": "HR", "tag": None,
     "desc": "Headcount, lifecycle stage and visa expiries across the whole team."},
    {"key": "deals", "title": "Deals Dashboard", "dept": "TXN", "tag": None,
     "desc": "Transaction pipeline, docs status and the commission approval queue."},
    {"key": "leads", "title": "Leads Dashboard", "dept": "SAL", "tag": None,
     "desc": "Sales pipeline, follow-ups due within 7 days and lead source mix."},
    {"key": "hr", "title": "HR Dashboard", "dept": "HR", "tag": "New",
     "desc": "Employee lifecycle funnel, leave approvals and open discipline/grievance items."},
    {"key": "payroll", "title": "Payroll Dashboard", "dept": "PAY", "tag": "New",
     "desc": "Payroll runs, salary cost and pending salary advances."},
    {"key": "recruitment", "title": "Recruitment Dashboard", "dept": "REC", "tag": "New",
     "desc": "Open requisitions and the candidate pipeline, applied to hired."},
    {"key": "attendance", "title": "Attendance Dashboard", "dept": "ATT", "tag": "New",
     "desc": "Today's attendance mix and the monthly attendance rate."},
    {"key": "finance", "title": "Finance Dashboard", "dept": "FIN", "tag": "New",
     "desc": "Payment/expense approval queue and the petty-cash balance."},
    {"key": "it-admin", "title": "IT Admin Dashboard", "dept": "IT", "tag": "New",
     "desc": "System access, admin accounts needing review and open security incidents."},
    {"key": "asset", "title": "Asset Dashboard", "dept": "IT", "tag": "New",
     "desc": "The company asset register — by type, status and warranty expiry."},
    {"key": "helpdesk", "title": "Help Desk Dashboard", "dept": "HLP", "tag": "New",
     "desc": "Open tickets by priority/category and general requests pending."},
    {"key": "marketing", "title": "Marketing Dashboard", "dept": "MKT", "tag": "New",
     "desc": "Live campaigns, advertising permits expiring, content awaiting approval and leads handed to Sales."},
]
DASHBOARDS_BY_KEY = {d["key"]: d for d in DASHBOARDS}


def _employee():
    panels = []
    first_of_month = date.today().replace(day=1).isoformat()

    total_headcount = db.count_records("HR-002")
    active = db.count_where_in("HR-002", "status", ["Active"])
    new_joiners = db.count_where("HR-002", [("start_date", "gte", first_of_month)])
    exits_month = db.count_where("HR-013", [("last_working_day", "gte", first_of_month)])
    visa_upcoming_all = db.records_upcoming("HR-002", "visa_expiry", days_ahead=90, limit=1000)

    panels.append({"type": "kpis", "kpis": [
        _kpi("Total headcount", total_headcount, "blue"),
        _kpi("Active headcount", active, "green"),
        _kpi("New joiners this month", new_joiners, "green" if new_joiners else "neutral"),
        _kpi("Exits this month", exits_month, "red" if exits_month else "green"),
        _kpi("Visas expiring ≤ 90 days", len(visa_upcoming_all), "red" if visa_upcoming_all else "green"),
    ]})

    dept_bars = db.field_counts("HR-002", "department")
    if dept_bars:
        panels.append({"type": "breakdown", "title": "Headcount by Department", "bars": _bars_from_counts(dept_bars)})

    type_bars = db.field_counts("HR-002", "employment_type")
    if type_bars:
        panels.append({"type": "breakdown", "title": "Employment Type Mix", "bars": _bars_from_counts(type_bars)})

    panels.append({"type": "list", "title": "Visa Expiries Within 90 Days", "icon": "id-card",
                    "empty_text": "No visa expiries in the next 90 days.",
                    "rows": [{"form_code": "HR-002", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("full_name") or r["doc_no"],
                               "meta": "expires {} ({}d)".format(r.get("visa_expiry") or "—", r["_days"]),
                               "tone": "RED" if r["_days"] <= 30 else "AMBER"} for r in visa_upcoming_all[:8]]})
    return panels


def _it_admin():
    panels = []
    active_access = db.count_where_in("IT-005", "status", ["Active"])
    total_access = db.count_records("IT-005")
    admin_review = db.count_where_in("IT-006", "status", ["Needs Review"])
    admin_total = db.count_records("IT-006")
    incidents_open = db.count_where_in("IT-008", "status", ["Open", "Investigating"])

    panels.append({"type": "kpis", "kpis": [
        _kpi("Active system access grants", "{}/{}".format(active_access, total_access), "green"),
        _kpi("Admin accounts on file", admin_total, "blue"),
        _kpi("Admin accounts needing review", admin_review, "amber" if admin_review else "green"),
        _kpi("Open security incidents", incidents_open, "red" if incidents_open else "green"),
    ]})

    system_bars = db.field_counts("IT-005", "system")
    if system_bars:
        panels.append({"type": "breakdown", "title": "Access Grants by System", "bars": _bars_from_counts(system_bars)})

    incidents = db.records_where_in("IT-008", "status", ["Open", "Investigating"], limit=8)
    panels.append({"type": "list", "title": "Open Security Incidents", "icon": "alert-triangle",
                    "empty_text": "No open security incidents.",
                    "rows": [{"form_code": "IT-008", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("incident_type") or r["doc_no"],
                               "meta": "reported by {} · {}".format(r.get("reported_by") or "—", r.get("incident_date") or "—"),
                               "tone": "RED"} for r in incidents]})

    review_rows = db.records_where_in("IT-006", "status", ["Needs Review"], limit=8)
    panels.append({"type": "list", "title": "Admin Accounts Needing Review", "icon": "lock",
                    "empty_text": "No admin accounts flagged for review.",
                    "rows": [{"form_code": "IT-006", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("system_platform") or r["doc_no"],
                               "meta": "owner {} · last reviewed {}".format(r.get("owner") or "—", r.get("last_reviewed") or "—"),
                               "tone": "AMBER"} for r in review_rows]})
    return panels


def _asset():
    panels = []
    total_assets = db.count_records("IT-001")
    in_use = db.count_where_in("IT-001", "status", ["In Use"])
    in_storage = db.count_where_in("IT-001", "status", ["In Storage"])
    retired = db.count_where_in("IT-001", "status", ["Retired"])
    warranty_upcoming = db.records_upcoming("IT-001", "warranty_expiry", days_ahead=90, limit=1000)

    panels.append({"type": "kpis", "kpis": [
        _kpi("Total assets on register", total_assets, "blue"),
        _kpi("In use", in_use, "green"),
        _kpi("In storage", in_storage, "blue"),
        _kpi("Retired", retired, "neutral"),
        _kpi("Warranty expiring ≤ 90 days", len(warranty_upcoming), "amber" if warranty_upcoming else "green"),
    ]})

    type_bars = db.field_counts("IT-001", "asset_type")
    if type_bars:
        panels.append({"type": "breakdown", "title": "Asset Register by Type", "bars": _bars_from_counts(type_bars)})

    panels.append({"type": "list", "title": "Warranty Expiring Soon", "icon": "archive",
                    "empty_text": "No warranties expiring in the next 90 days.",
                    "rows": [{"form_code": "IT-001", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": "{} · {}".format(r.get("asset_type") or "Asset", r.get("serial_number") or r["doc_no"]),
                               "meta": "assigned to {} · expires {} ({}d)".format(
                                   r.get("assigned_employee") or "—", r.get("warranty_expiry") or "—", r["_days"]),
                               "tone": "RED" if r["_days"] <= 30 else "AMBER"} for r in warranty_upcoming[:8]]})

    issued_rows = db.records_where_in("IT-002", "status", ["Issued"], limit=8)
    panels.append({"type": "list", "title": "Issued, Not Yet Returned", "icon": "check-square",
                    "empty_text": "No outstanding asset handovers.",
                    "rows": [{"form_code": "IT-002", "record_id": r["id"], "doc_no": r["doc_no"],
                               "title": r.get("employee_name") or r["doc_no"],
                               "meta": "asset {} · issued {}".format(r.get("asset_ref") or "—", r.get("date_issued") or "—"),
                               "tone": "BLUE"} for r in issued_rows]})
    return panels


_DASHBOARD_BUILDERS = {"employee": _employee, "it-admin": _it_admin, "asset": _asset}


def dashboard_panels(key):
    d = DASHBOARDS_BY_KEY.get(key)
    if not d:
        return []
    fn = _DASHBOARD_BUILDERS.get(key)
    try:
        if fn:
            return fn()
        if d.get("dept"):
            return build(d["dept"])
        return []
    except Exception:
        return []
