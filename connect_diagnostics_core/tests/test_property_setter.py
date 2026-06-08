# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path

from erpnext_thailand.custom.naming import parse_naming_series_variable
from frappe import _dict
from frappe.model.naming import parse_naming_series
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

import connect_diagnostics_core

FIXTURE_PATH = Path(connect_diagnostics_core.__file__).parent / "fixtures" / "property_setter.json"
CUSTOMIZATION_PATH = Path(connect_diagnostics_core.__file__).parent / "connect_diagnostics_core" / "custom"
DOCUMENT_DATE_FIELDS = {
    "Asset Capitalization": "posting_date",
    "Bank Transaction": "date",
    "Delivery Note": "posting_date",
    "Dunning": "posting_date",
    "Employee Advance": "posting_date",
    "Expense Claim": "posting_date",
    "Job Card": "posting_date",
    "Job Requisition": "posting_date",
    "Journal Entry": "posting_date",
    "Landed Cost Voucher": "posting_date",
    "Leave Application": "posting_date",
    "Material Request": "transaction_date",
    "POS Invoice": "posting_date",
    "Payment Entry": "posting_date",
    "Payment Order": "posting_date",
    "Payment Request": "transaction_date",
    "Production Plan": "posting_date",
    "Purchase Invoice": "posting_date",
    "Purchase Order": "transaction_date",
    "Purchase Receipt": "posting_date",
    "Quotation": "transaction_date",
    "Request for Quotation": "transaction_date",
    "Sales Invoice": "posting_date",
    "Sales Order": "transaction_date",
    "Stock Entry": "posting_date",
    "Stock Reconciliation": "posting_date",
    "Subcontracting Receipt": "posting_date",
    "Supplier Quotation": "transaction_date",
}


def _load_fixture() -> list[dict]:
    with FIXTURE_PATH.open() as f:
        return json.load(f)


class TestNamingSeriesPropertySetters(FrappeTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.rows = _load_fixture()
        cls.options_rows = {
            r["doc_type"]: r
            for r in cls.rows
            if r.get("field_name") == "naming_series" and r.get("property") == "options"
        }
        cls.default_rows = {
            r["doc_type"]: r
            for r in cls.rows
            if r.get("field_name") == "naming_series" and r.get("property") == "default"
        }

    def test_every_options_setter_has_matching_default(self) -> None:
        missing = sorted(set(self.options_rows) - set(self.default_rows))
        self.assertFalse(
            missing,
            f"naming_series options set without a matching default property setter for: {missing}. "
            "Add a `<DocType>-naming_series-default` row whose value is one of the options.",
        )

    def test_default_value_is_present_in_options(self) -> None:
        mismatches: list[str] = []
        for doc_type, default_row in self.default_rows.items():
            options_row = self.options_rows.get(doc_type)
            if not options_row:
                mismatches.append(f"{doc_type}: default set without matching options")
                continue
            default_value = (default_row.get("value") or "").strip()
            options = [o.strip() for o in (options_row.get("value") or "").split("\n") if o.strip()]
            if default_value not in options:
                mismatches.append(f"{doc_type}: default {default_value!r} not in options {options!r}")
        self.assertFalse(
            mismatches,
            "naming_series default does not match options list:\n  " + "\n  ".join(mismatches),
        )

    def test_document_date_doctypes_use_document_date_tokens(self) -> None:
        for doc_type in DOCUMENT_DATE_FIELDS:
            with self.subTest(doc_type=doc_type):
                default = self.default_rows[doc_type]["value"]
                options = self.options_rows[doc_type]["value"].splitlines()
                self.assertIn(".YY-BE.MM-DATE.", default)
                self.assertTrue(options)
                self.assertTrue(all(".YY-BE.MM-DATE." in option for option in options))

    def test_customization_exports_match_fixture_naming_series(self) -> None:
        for doc_type in ("Employee", "Purchase Invoice", "Sales Invoice"):
            with self.subTest(doc_type=doc_type):
                customization = json.loads(
                    (CUSTOMIZATION_PATH / f"{doc_type.lower().replace(' ', '_')}.json").read_text()
                )
                setters = {
                    row["property"]: row["value"]
                    for row in customization["property_setters"]
                    if row.get("field_name") == "naming_series"
                    and row.get("property") in ("default", "options")
                }
                self.assertEqual(setters["options"], self.options_rows[doc_type]["value"])
                if "default" in setters:
                    self.assertEqual(setters["default"], self.default_rows[doc_type]["value"])

    def test_document_date_tokens_use_posting_date(self) -> None:
        doc = _dict(posting_date="2025-03-15", transaction_date="2024-02-10", date="2023-01-05")
        self.assertEqual(parse_naming_series_variable(doc, "YY-DATE"), "25")
        self.assertEqual(parse_naming_series_variable(doc, "MM-DATE"), "03")

    def test_document_date_tokens_fall_back_to_transaction_date(self) -> None:
        doc = _dict(transaction_date=getdate("2024-02-10"), date="2023-01-05")
        self.assertEqual(parse_naming_series_variable(doc, "YY-DATE"), "24")
        self.assertEqual(parse_naming_series_variable(doc, "MM-DATE"), "02")

    def test_naming_series_generates_name_from_posting_date(self) -> None:
        doc = _dict(posting_date="2025-03-15")

        def generate_number(_prefix, _digits):
            return "0001"

        self.assertEqual(
            # pyrefly: ignore [bad-argument-type]
            parse_naming_series("SI.YY-DATE.MM-DATE.####", doc=doc, number_generator=generate_number),
            "SI25030001",
        )
        self.assertEqual(
            # pyrefly: ignore [bad-argument-type]
            parse_naming_series("ICJE.YY-DATE.MM-DATE.####", doc=doc, number_generator=generate_number),
            "ICJE25030001",
        )

    def test_naming_series_generates_name_from_each_document_date_field(self) -> None:
        def generate_number(_prefix, _digits):
            return "0001"

        for doc_type, date_field in DOCUMENT_DATE_FIELDS.items():
            with self.subTest(doc_type=doc_type, date_field=date_field):
                doc = _dict({date_field: "2025-03-15"})
                series = self.default_rows[doc_type]["value"]
                self.assertIn(
                    "6803",
                    # pyrefly: ignore [bad-argument-type]
                    parse_naming_series(series, doc=doc, number_generator=generate_number),
                )
