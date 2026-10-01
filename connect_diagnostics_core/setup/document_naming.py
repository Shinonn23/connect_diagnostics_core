# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Central naming policy for automatically numbered operational documents."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import frappe
from frappe.utils import get_datetime, getdate, today

YEAR_TOKEN = "YYYY-BE"
DATE_TOKEN = "MM-DATE"
SERIES_PATTERN = f"{YEAR_TOKEN}.{DATE_TOKEN}.####"

# Retained only for the historical broken-autoname data migration.
LEGACY_DATE_TOKEN = "MM-DOC"
AUTONAME_YEAR_TOKEN = "YYBE"
AUTONAME_DATE_TOKEN = "MMDOC"

# These are intentionally explicit.  The registry is the source of truth for
# every operational DocType, including DocTypes owned by installed apps.
NAMING_SERIES_PREFIXES: dict[str, tuple[str, ...]] = {
    "Customer Credit Request": ("CCR",),
    "Supplier Bank Change Request": ("SBCR",),
    "Bank Transaction": ("BT",),
    "Budget": ("BUD",),
    "Cashier Closing": ("CC",),
    "Dunning": ("DUN",),
    "Journal Entry": (
        "JE",
        "ICJE",
        "BK",
        "CE",
        "CC",
        "DN",
        "CN",
        "CT",
        "EX",
        "WO",
        "OP",
        "DP",
        "ERR",
        "EGL",
        "DR",
        "DE",
    ),
    "Payment Entry": ("PE",),
    "Payment Order": ("PAYO",),
    "Payment Request": ("PRQ",),
    "POS Invoice": ("POSI",),
    "Asset": ("AST",),
    "Asset Capitalization": ("AC",),
    "Asset Depreciation Schedule": ("ADS",),
    "Asset Maintenance Log": ("AML",),
    "Asset Repair": ("AR",),
    "Asset Shift Allocation": ("ASA",),
    "Purchase Invoice": ("PI",),
    "Sales Invoice": ("SI", "CN"),
    "Purchase Order": ("PO",),
    "Request for Quotation": ("RFQ",),
    "Supplier Quotation": ("SQ",),
    "Supplier Scorecard Period": ("SSP",),
    "Campaign": ("CMP",),
    "Lead": ("LE",),
    "Opportunity": ("OPP",),
    "Maintenance Schedule": ("MS",),
    "Maintenance Visit": ("MV",),
    "Blanket Order": ("BO",),
    "Downtime Entry": ("DE",),
    "Job Card": ("JC",),
    "Master Production Schedule": ("MPS",),
    "Production Plan": ("PP",),
    "Sales Forecast": ("SF",),
    "Work Order": ("WO",),
    "Project": ("PRJ",),
    "Project Update": ("PU",),
    "Timesheet": ("TS",),
    "Installation Note": ("IN",),
    "Quotation": ("QT",),
    "Sales Order": ("SO",),
    "Delivery Note": ("DN",),
    "Delivery Trip": ("DT",),
    "Landed Cost Voucher": ("LCV",),
    "Material Request": ("MR",),
    "Dispatch": ("DSP",),
    "Borrowed Asset Return Inspection": ("BARI",),
    "Borrowed Item Resolution": ("BIR",),
    "Packing Slip": ("PS",),
    "Pick List": ("PL",),
    "Purchase Receipt": ("PR",),
    "Quality Inspection": ("QI",),
    "Stock Closing Entry": ("SCE",),
    "Stock Entry": ("SE",),
    "Stock Borrow": ("SBR",),
    "Stock Reconciliation": ("SR",),
    "Stock Asset Conversion": ("SAC",),
    "Material Request Fulfillment": ("MRF",),
    "Subcontracting Inward Order": ("SIO",),
    "Subcontracting Order": ("SCO",),
    "Subcontracting Receipt": ("SCR",),
    "Issue": ("ISS",),
    "Warranty Claim": ("WC",),
    "Payment Receipt": ("RE", "RV"),
    "Purchase Billing": ("PB",),
    "Sales Billing": ("SB",),
    "Purchase Tax Invoice": ("PTI",),
    "Sales Tax Invoice": ("STI",),
    "Appraisal": ("AP",),
    "Attendance": ("ATT",),
    "Employee Advance": ("EA",),
    "Exit Interview": ("EI",),
    "Expense Claim": ("EC",),
    "Holiday List Assignment": ("HLA",),
    "Job Requisition": ("JR",),
    "Leave Adjustment": ("LADJ",),
    "Leave Allocation": ("LA",),
    "Leave Application": ("LAP",),
    "Vehicle Log": ("VL",),
    "Additional Salary": ("AS",),
}

AUTONAME_PREFIXES: dict[str, str] = {
    "Bank Guarantee": "BGT",
    "Cost Center Allocation": "CCA",
    "Exchange Rate Revaluation": "ERR",
    "Invoice Discounting": "ID",
    "Period Closing Voucher": "PCV",
    "POS Closing Entry": "PCE",
    "POS Opening Entry": "POE",
    "Process Deferred Accounting": "PDA",
    "Process Payment Reconciliation": "PPR",
    "Process Period Closing Voucher": "PPCV",
    "Share Transfer": "SHT",
    "Asset Movement": "AM",
    "Contract": "CON",
    "Shipment": "SHP",
    "Stock Reservation Entry": "SRE",
    "Withholding Tax Cert": "WHT",
    "Attendance Request": "ARQ",
    "Compensatory Leave Request": "CLR",
    "Employee Grievance": "EG",
    "Employee Onboarding": "EON",
    "Employee Performance Feedback": "EPF",
    "Employee Promotion": "EPR",
    "Employee Referral": "ER",
    "Employee Separation": "ES",
    "Employee Transfer": "ET",
    "Full and Final Statement": "FNF",
    "Interview": "INT",
    "Interview Feedback": "IF",
    "Job Offer": "JO",
    "Leave Encashment": "LE",
    "Leave Policy": "LP",
    "Leave Policy Assignment": "LPA",
    "Overtime Slip": "OTS",
    "Shift Assignment": "SHA",
    "Shift Request": "SHR",
    "Training Feedback": "TF",
    "Training Result": "TR",
    "Travel Request": "TRQ",
    "Arrear": "ARR",
    "Employee Benefit Application": "EBA",
    "Employee Benefit Claim": "EBC",
    "Employee Incentive": "EIN",
    "Employee Other Income": "EOI",
    "Employee Tax Exemption Declaration": "ETD",
    "Employee Tax Exemption Proof Submission": "ETP",
    "Gratuity": "GRA",
    "Payroll Entry": "PAY",
    "Retention Bonus": "RB",
    "Salary Structure Assignment": "SSA",
}

JOURNAL_ENTRY_PREFIXES = {
    "Journal Entry": "JE",
    "Inter Company Journal Entry": "ICJE",
    "Bank Entry": "BK",
    "Cash Entry": "CE",
    "Credit Card Entry": "CC",
    "Debit Note": "DN",
    "Credit Note": "CN",
    "Contra Entry": "CT",
    "Excise Entry": "EX",
    "Write Off Entry": "WO",
    "Opening Entry": "OP",
    "Depreciation Entry": "DP",
    "Asset Disposal": "DR",
    "Exchange Rate Revaluation": "ERR",
    "Exchange Gain Or Loss": "EGL",
    "Deferred Revenue": "DR",
    "Deferred Expense": "DE",
}


def series_options(prefixes: Iterable[str]) -> str:
    return "\n".join(f"{prefix}.{SERIES_PATTERN}" for prefix in prefixes)


def property_setters() -> dict[str, list[tuple[str | None, str, str, str]]]:
    setters: dict[str, list[tuple[str | None, str, str, str]]] = {}
    for doctype, prefixes in NAMING_SERIES_PREFIXES.items():
        options = series_options(prefixes)
        setters[doctype] = [
            ("naming_series", "default", options.splitlines()[0], "Text"),
            ("naming_series", "options", options, "Text"),
            ("naming_series", "hidden", "1", "Check"),
        ]

    for doctype, prefix in AUTONAME_PREFIXES.items():
        setters.setdefault(doctype, []).append(
            (
                None,
                "autoname",
                f"{prefix}.{SERIES_PATTERN}",
                "Data",
            )
        )
    return setters


def parse_document_month(doc: Any, variable: str) -> str | None:
    """Resolve legacy month tokens used by the historical autoname backfill."""
    if variable not in (LEGACY_DATE_TOKEN, AUTONAME_DATE_TOKEN):
        return None
    return f"{_document_date(doc).month:02d}"


def set_operational_naming_series(doc: Any, method: str | None = None) -> None:
    """Select the registered series from document business fields."""
    if getattr(doc, "meta", None) and doc.meta.istable:
        return
    if doc.get("amended_from") or doc.doctype not in NAMING_SERIES_PREFIXES:
        return

    prefix = _resolve_prefix(doc)
    doc.naming_series = f"{prefix}.{SERIES_PATTERN}"


def _resolve_prefix(doc: Any) -> str:
    if doc.doctype == "Sales Invoice":
        return "CN" if doc.get("is_return") else "SI"

    if doc.doctype == "Journal Entry":
        return JOURNAL_ENTRY_PREFIXES.get(doc.get("voucher_type"), "JE")

    if doc.doctype == "Payment Receipt":
        return _payment_receipt_prefix(doc)

    return NAMING_SERIES_PREFIXES[doc.doctype][0]


def _payment_receipt_prefix(doc: Any) -> str:
    payment_types: set[str] = set()
    for reference in doc.get("payment_references") or []:
        payment_entry = reference.get("payment_entry")
        if payment_entry:
            payment_type = frappe.db.get_value("Payment Entry", payment_entry, "payment_type")
            if payment_type:
                payment_types.add(str(payment_type))

    if payment_types == {"Pay"}:
        return "RV"
    return "RE"


def _document_date(doc: Any) -> date:
    for fieldname in (
        "posting_date",
        "budget_start_date",
        "transaction_date",
        "attendance_date",
        "date",
        "date_of_joining",
        "document_date",
        "purchase_date",
        "expected_start_date",
        "campaign_start_date",
        "schedule_date",
        "visit_date",
        "repair_date",
        "issue_date",
        "report_date",
        "start_date",
        "from_date",
    ):
        value = doc.get(fieldname) if hasattr(doc, "get") else getattr(doc, fieldname, None)
        if value:
            parsed = getdate(value)
            if parsed is not None:
                return parsed

    creation = doc.get("creation") if hasattr(doc, "get") else getattr(doc, "creation", None)
    if creation:
        parsed_creation = get_datetime(creation)
        if parsed_creation is not None:
            return parsed_creation.date()

    parsed_today = getdate(today())
    if parsed_today is None:
        raise ValueError("Unable to determine a document date for naming")
    return parsed_today


PROPERTY_SETTERS = property_setters()


def apply() -> None:
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    for doctype, setters in PROPERTY_SETTERS.items():
        for fieldname, prop, value, property_type in setters:
            make_property_setter(
                doctype,
                fieldname,
                prop,
                value,
                property_type,
                for_doctype=fieldname is None,
                validate_fields_for_doctype=False,
            )
        frappe.clear_cache(doctype=doctype)
