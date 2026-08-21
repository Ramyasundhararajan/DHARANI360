# -*- coding: utf-8 -*-
"""
DHARANI 360 - demo records
=============================
Fills a realistic slice of the registers so a demo has something to show.
Without this the system opens on 112 empty tables, which demonstrates
nothing.

Everything written here is tagged "[demo]" in its Notes field, so a single
search for that word finds all of it when you want it gone.

Run:   python demo_data.py

Safe to run twice - it checks whether demo records already exist and stops
rather than doubling them up. Expiry dates are written relative to today, so
the compliance calendar always opens with something red, something amber and
something green no matter when the demo is shown.
"""
import os
import sys
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import db                                   # noqa: E402
from forms_data import FORMS_BY_CODE        # noqa: E402

TAG = "[demo]"
TODAY = date.today()


def d(days):
    """A date this many days from today, as the app stores dates."""
    return (TODAY + timedelta(days=days)).isoformat()


# --- the records -----------------------------------------------------------
# Kept in one table so the whole demo can be read at a glance and edited
# without touching code.
RECORDS = [
    # Licences and permits: one overdue, one urgent, one comfortable. This is
    # what makes the bell and the compliance calendar worth looking at.
    ("COR-002", {"licence_permit": "Trade Licence", "authority": "Dept. of Economy & Tourism",
                 "reference_no": "DET-772451", "issue_date": d(-355), "expiry_date": d(-6),
                 "renewal_lead_time_days": 90, "responsible_person": "Khalida Amyn"}, "Overdue"),
    ("COR-002", {"licence_permit": "RERA Brokerage Registration", "authority": "RERA / Dubai Land Department",
                 "reference_no": "RERA-24418", "issue_date": d(-330), "expiry_date": d(21),
                 "renewal_lead_time_days": 90, "responsible_person": "Akbar Hassan Dharani"}, "Active"),
    ("COR-002", {"licence_permit": "Establishment Card", "authority": "GDRFA Dubai",
                 "reference_no": "GD-90233", "issue_date": d(-250), "expiry_date": d(48),
                 "renewal_lead_time_days": 60, "responsible_person": "Khalida Amyn"}, "Active"),
    ("COR-002", {"licence_permit": "Chamber of Commerce Membership", "authority": "Dubai Chambers",
                 "reference_no": "DC-11902", "issue_date": d(-190), "expiry_date": d(174),
                 "renewal_lead_time_days": 60, "responsible_person": "Khalida Amyn"}, "Active"),

    # Agents, one card close to expiry
    ("AGT-002", {"agent_name": "Baqeer Muhammed", "phone": "+971 50 118 4420",
                 "email": "baqeer@dharanis.ae", "broker_card_no": "BRK-55210",
                 "broker_card_expiry": d(27), "passport_no": "P4482119",
                 "emirates_id_no": "784-1990-1122334-1", "visa_expiry": d(210),
                 "commission_structure": "50% of company share"}, "Active"),
    ("AGT-002", {"agent_name": "Sana Qureshi", "phone": "+971 55 640 2277",
                 "email": "sana@dharanis.ae", "broker_card_no": "BRK-55984",
                 "broker_card_expiry": d(146), "passport_no": "P7719004",
                 "emirates_id_no": "784-1994-8890112-6", "visa_expiry": d(320),
                 "commission_structure": "45% of company share"}, "Active"),

    # Properties
    ("PRO-001", {"property_ref": "DR-P-1041", "owner_name": "Ahmed Al Mansoori",
                 "location": "Business Bay", "unit_no": "2104", "building": "Bay Square Tower 3",
                 "property_type": "Apartment", "asking_price": 1850000, "availability": "Available"}, "Active"),
    ("PRO-001", {"property_ref": "DR-P-1042", "owner_name": "Fatima Hassan",
                 "location": "Jumeirah Village Circle", "unit_no": "villa 12", "building": "District 14",
                 "property_type": "Villa", "asking_price": 3250000, "availability": "Available"}, "Active"),
    ("PRO-001", {"property_ref": "DR-P-1043", "owner_name": "Rashid Property Co",
                 "location": "Dubai Marina", "unit_no": "1806", "building": "Marina Heights",
                 "property_type": "Apartment", "asking_price": 2100000, "availability": "Reserved"}, "Active"),
    ("PRO-001", {"property_ref": "DR-P-1044", "owner_name": "Sunil Menon",
                 "location": "Al Barsha South", "unit_no": "office 402", "building": "Barsha Business Centre",
                 "property_type": "Office", "asking_price": 1420000, "availability": "Available"}, "Active"),

    # Leads
    ("SAL-001", {"lead_id": "L-2291", "date_received": d(-11), "source": "Website",
                 "client_name": "Priya Nair", "contact": "+971 52 331 7788",
                 "property_interest": "2BR Business Bay", "agent_assigned": "Baqeer Muhammed"}, "Qualified"),
    ("SAL-001", {"lead_id": "L-2292", "date_received": d(-9), "source": "Referral",
                 "client_name": "Omar Al Suwaidi", "contact": "+971 50 442 1190",
                 "property_interest": "Villa JVC", "agent_assigned": "Sana Qureshi"}, "Qualified"),
    ("SAL-001", {"lead_id": "L-2293", "date_received": d(-6), "source": "Property Portal",
                 "client_name": "Jane Whitfield", "contact": "+971 55 907 6612",
                 "property_interest": "Marina apartment", "agent_assigned": "Baqeer Muhammed"}, "In Progress"),
    ("SAL-001", {"lead_id": "L-2294", "date_received": d(-3), "source": "Walk-in",
                 "client_name": "Vikram Shah", "contact": "+971 56 220 4431",
                 "property_interest": "Office Al Barsha", "agent_assigned": "Sana Qureshi"}, "New"),
    ("SAL-001", {"lead_id": "L-2295", "date_received": d(-1), "source": "Social Media",
                 "client_name": "Leila Haddad", "contact": "+971 50 771 3390",
                 "property_interest": "2BR Marina", "agent_assigned": "Baqeer Muhammed"}, "New"),

    # Viewings
    ("SAL-005", {"client_name": "Priya Nair", "property_ref": "DR-P-1041", "agent": "Baqeer Muhammed",
                 "viewing_date": d(-5),
                 "feedback": "Liked the layout, asked about service charges and handover date."}, "Completed"),
    ("SAL-005", {"client_name": "Omar Al Suwaidi", "property_ref": "DR-P-1042", "agent": "Sana Qureshi",
                 "viewing_date": d(-4),
                 "feedback": "Wants a second viewing with his wife. Concerned about garden maintenance."}, "Completed"),
    ("SAL-005", {"client_name": "Jane Whitfield", "property_ref": "DR-P-1043", "agent": "Baqeer Muhammed",
                 "viewing_date": d(-2),
                 "feedback": "Very interested. Asked us to hold it for 48 hours."}, "Completed"),

    # Offers
    ("SAL-007", {"client_name": "Priya Nair", "property_ref": "DR-P-1041", "offer_amount": 1760000,
                 "counter_offer": 1815000, "agent": "Baqeer Muhammed", "date": d(-3)}, "In Progress"),
    ("SAL-007", {"client_name": "Jane Whitfield", "property_ref": "DR-P-1043", "offer_amount": 2050000,
                 "counter_offer": 2075000, "agent": "Baqeer Muhammed", "date": d(-1)}, "In Progress"),

    # A deal in flight
    ("TXN-001", {"transaction_ref": "DR-T-3310", "property_ref": "DR-P-1043",
                 "client_name": "Jane Whitfield", "agent": "Baqeer Muhammed",
                 "transaction_type": "Sale", "opened_date": d(-1)}, "In Progress"),
    ("TXN-003", {"transaction_ref": "DR-T-3310", "transaction_value": 2075000,
                 "company_commission_pct": 2, "company_commission_amount": 41500,
                 "agent_pct": 50, "agent_commission_amount": 20750}, "Pending Approval"),

    # KYC
    ("CMP-001", {"client_name": "Jane Whitfield", "id_verified": "Yes", "address_verified": "Yes",
                 "source_of_funds_verified": "Yes", "pep_screening": "Clear",
                 "sanctions_screening": "Clear", "completed_by": "Khalida Amyn", "date": d(-1)}, "Completed"),
    ("CMP-001", {"client_name": "Priya Nair", "id_verified": "Yes", "address_verified": "Pending",
                 "source_of_funds_verified": "Pending", "pep_screening": "Clear",
                 "sanctions_screening": "Clear", "completed_by": "Khalida Amyn", "date": d(-3)}, "In Progress"),

    # Finance
    ("FIN-001", {"employee_name": "Baqeer Muhammed", "expense_date": d(-8), "category": "Travel",
                 "amount": 420, "description": "Client viewings, Business Bay and Marina.",
                 "approved_by": "Akbar Hassan Dharani"}, "Approved"),
    ("FIN-001", {"employee_name": "Greetus", "expense_date": d(-4), "category": "Marketing",
                 "amount": 1850, "description": "Portal listing credits for four properties.",
                 "approved_by": ""}, "Pending Approval"),
    ("FIN-001", {"employee_name": "Khalida Amyn", "expense_date": d(-2), "category": "Office",
                 "amount": 265, "description": "Printer toner and stationery.",
                 "approved_by": ""}, "Pending Approval"),

    # HR
    ("HR-007", {"employee_name": "Sana Qureshi", "leave_type": "Annual Leave", "from_date": d(14),
                 "to_date": d(21), "days": 8, "reason": "Family visit.",
                 "approved_by": "Akbar Hassan Dharani"}, "Approved"),
    ("HR-007", {"employee_name": "Greetus", "leave_type": "Sick Leave", "from_date": d(-2),
                 "to_date": d(-1), "days": 2, "reason": "Medical certificate attached.",
                 "approved_by": "Khalida Amyn"}, "Approved"),

    # IT assets, one warranty running out
    ("IT-001", {"asset_type": "Laptop", "serial_number": "SN-DL-99412", "purchase_date": d(-700),
                "cost": 4200, "assigned_employee": "Ramya", "condition": "Good",
                "location": "Head Office", "warranty_expiry": d(12)}, "Active"),
    ("IT-001", {"asset_type": "Laptop", "serial_number": "SN-HP-77120", "purchase_date": d(-400),
                "cost": 3800, "assigned_employee": "Baqeer Muhammed", "condition": "Good",
                "location": "Head Office", "warranty_expiry": d(330)}, "Active"),
    ("IT-001", {"asset_type": "Mobile Phone", "serial_number": "IMEI-3391182", "purchase_date": d(-210),
                "cost": 2600, "assigned_employee": "Sana Qureshi", "condition": "Good",
                "location": "With employee", "warranty_expiry": d(155)}, "Active"),

    # Marketing
    ("MKT-001", {"campaign_ref": "C-0148", "campaign_name": "Marina Heights launch",
                 "campaign_type": "Digital", "objective": "Generate qualified buyer leads for DR-P-1043.",
                 "target_audience": "Buyers 30-50, Dubai and GCC, AED 1.8m-2.4m budget.",
                 "primary_channel": "Instagram", "property_ref": "DR-P-1043",
                 "requested_by": "Greetus", "proposed_start_date": d(-14),
                 "proposed_end_date": d(16), "estimated_budget_aed": 9500,
                 "expected_leads": 60, "approved_by": "Akbar Hassan Dharani",
                 "approval_date": d(-15)}, "In Progress"),
]


def already_seeded():
    """True if demo records are present, so a second run does nothing."""
    try:
        rows, _ = db.get_records("SAL-001")
    except Exception:
        return False
    return any(TAG in (r.get("notes") or "") for r in rows)


def main():
    db.init_db()

    if already_seeded():
        print("\n  Demo records are already here. Nothing to do.")
        print("  To start again: search for \"{}\" and delete those records.\n".format(TAG))
        return 0

    print("\n" + "=" * 64)
    print("  DHARANI 360 - loading demo records")
    print("=" * 64 + "\n")

    made, skipped = 0, []
    for code, values, status in RECORDS:
        form = FORMS_BY_CODE.get(code)
        if not form:
            skipped.append(code + " (no such register)")
            continue
        allowed = {f["name"] for f in form["fields"]}
        clean = {k: v for k, v in values.items() if k in allowed}
        clean["status"] = status
        clean["notes"] = TAG + " sample record for demonstration - safe to delete."
        try:
            db.insert_record(code, clean, created_by="Demo data")
            made += 1
        except Exception as exc:
            skipped.append("{} ({})".format(code, exc))

    by_form = {}
    for code, _v, _s in RECORDS:
        by_form[code] = by_form.get(code, 0) + 1
    for code in sorted(by_form):
        title = FORMS_BY_CODE[code]["title"] if code in FORMS_BY_CODE else code
        print("    {:<10} {:<38} {:>2}".format(code, title[:38], by_form[code]))

    print("\n  {} records created.".format(made))
    if skipped:
        print("  Skipped: " + ", ".join(skipped))
    print("\n  Dates are relative to today, so the compliance calendar always")
    print("  shows one overdue item, one due within 30 days, and several")
    print("  further out.")
    print("\n  Every record is tagged \"{}\" in Notes - search for that to".format(TAG))
    print("  find and remove them all.")
    print("=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
