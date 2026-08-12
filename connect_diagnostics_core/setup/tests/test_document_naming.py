# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock, patch

from frappe.model.document import Document
from frappe.model.naming import parse_naming_series
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import document_naming
from connect_diagnostics_core.api.erpnext.employee import parse_buddhist_era_naming_series_variable


class TestDocumentNaming(UnitTestCase):
    def test_series_options_render_four_digit_document_numbers(self) -> None:
        options = document_naming.series_options(("SI", "CN"))

        self.assertEqual(options, "SI.YY-BE.MM-DOC.####\nCN.YY-BE.MM-DOC.####")
        self.assertNotIn("-DATE", options)

    @patch("frappe.model.naming.has_custom_parser")
    def test_series_renders_the_go_live_shape(self, custom_parser: MagicMock) -> None:
        custom_parser.side_effect = lambda token: {
            "YY-BE": (
                "connect_diagnostics_core.api.erpnext.employee.parse_buddhist_era_naming_series_variable",
            ),
            "MM-DOC": ("connect_diagnostics_core.setup.document_naming.parse_document_month",),
        }.get(token)
        doc = SimpleNamespace(
            get=lambda field, default=None: {"posting_date": "2026-07-31"}.get(field, default)
        )

        name = parse_naming_series(
            "SI.YY-BE.MM-DOC.####",
            doc=cast(Document, doc),
            number_generator=lambda _prefix, _digits: "0001",
        )

        self.assertEqual(name, "SI69070001")

    def test_document_month_uses_transaction_date(self) -> None:
        doc = SimpleNamespace(get=lambda field: {"posting_date": "2026-07-31"}.get(field))

        self.assertEqual(document_naming.parse_document_month(doc, "MM-DOC"), "07")

    def test_document_month_falls_back_to_creation_date(self) -> None:
        doc = SimpleNamespace(get=lambda field: {"creation": "2026-08-01 09:00:00"}.get(field))

        self.assertEqual(document_naming.parse_document_month(doc, "MM-DOC"), "08")

    def test_document_month_uses_asset_purchase_date(self) -> None:
        doc = SimpleNamespace(get=lambda field: {"purchase_date": "2026-06-15"}.get(field))

        self.assertEqual(document_naming.parse_document_month(doc, "MM-DOC"), "06")

    def test_document_month_uses_project_expected_start_date(self) -> None:
        doc = SimpleNamespace(get=lambda field: {"expected_start_date": "2026-05-01"}.get(field))

        self.assertEqual(document_naming.parse_document_month(doc, "MM-DOC"), "05")

    def test_document_month_uses_budget_start_date(self) -> None:
        doc = SimpleNamespace(
            get=lambda field: {"budget_start_date": "2026-08-01", "creation": "2026-07-31"}.get(field)
        )

        self.assertEqual(document_naming.parse_document_month(doc, "MM-DOC"), "08")

    def test_buddhist_year_uses_the_same_document_date(self) -> None:
        doc = SimpleNamespace(
            get=lambda field: {"purchase_date": "2027-01-01", "creation": "2026-12-31"}.get(field)
        )

        self.assertEqual(parse_buddhist_era_naming_series_variable(doc, "YY-BE"), "70")

    def test_unknown_date_token_returns_none(self) -> None:
        self.assertIsNone(document_naming.parse_document_month(MagicMock(), "MM"))

    def test_autoname_patterns_use_document_date_and_four_digits(self) -> None:
        setters = document_naming.PROPERTY_SETTERS["Attendance Request"]
        autoname = next(setter for setter in setters if setter[0] is None)

        self.assertEqual(
            autoname[2],
            "format:ARQ{YY-BE}{MM-DOC}{####}",
        )

    def test_sales_invoice_selects_credit_note_for_returns(self) -> None:
        doc = SimpleNamespace(
            doctype="Sales Invoice",
            meta=SimpleNamespace(istable=False),
            get=lambda field: {"is_return": 1}.get(field),
        )

        document_naming.set_operational_naming_series(doc)

        self.assertEqual(doc.naming_series, "CN.YY-BE.MM-DOC.####")

    def test_journal_entry_selects_series_from_voucher_type(self) -> None:
        doc = SimpleNamespace(
            doctype="Journal Entry",
            meta=SimpleNamespace(istable=False),
            get=lambda field: {"voucher_type": "Bank Entry"}.get(field),
        )

        document_naming.set_operational_naming_series(doc)

        self.assertEqual(doc.naming_series, "BK.YY-BE.MM-DOC.####")

    @patch.object(document_naming.frappe.db, "get_value", return_value="Pay")
    def test_payment_receipt_selects_payment_series(self, _get_value: MagicMock) -> None:
        doc = SimpleNamespace(
            doctype="Payment Receipt",
            meta=SimpleNamespace(istable=False),
            get=lambda field: {"payment_references": [{"payment_entry": "PE-0001"}]}.get(field),
        )

        document_naming.set_operational_naming_series(doc)

        self.assertEqual(doc.naming_series, "RV.YY-BE.MM-DOC.####")

    @patch.object(document_naming.frappe, "clear_cache")
    @patch.object(document_naming, "make_property_setter", create=True)
    def test_apply_installs_each_registered_setter(
        self, make_setter: MagicMock, _clear_cache: MagicMock
    ) -> None:
        with patch(
            "frappe.custom.doctype.property_setter.property_setter.make_property_setter",
            make_setter,
        ):
            document_naming.apply()

        self.assertGreaterEqual(make_setter.call_count, len(document_naming.NAMING_SERIES_PREFIXES))
