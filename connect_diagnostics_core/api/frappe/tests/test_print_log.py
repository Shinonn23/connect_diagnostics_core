# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.frappe import print_log


class FakeDocument(frappe._dict):
    def __init__(self, values: dict[str, Any] | None = None) -> None:
        super().__init__(values or {})
        self.flags = frappe._dict()


class RecorderHarness(UnitTestCase):
    """Capture Print Log inserts without touching the database."""

    def setUp(self) -> None:
        super().setUp()
        self.inserted: list[dict[str, Any]] = []
        self.commits = 0

        self.log = MagicMock()
        self.log.update.side_effect = lambda values: self.inserted.append(dict(values))

        new_doc = patch.object(print_log.frappe, "new_doc", return_value=self.log)
        commit = patch.object(print_log.frappe.db, "commit", side_effect=self._commit)
        rollback = patch.object(print_log.frappe.db, "rollback")
        db_get_value = patch.object(print_log.frappe.db, "get_value", return_value=None)
        get_meta = patch.object(print_log.frappe, "get_meta", return_value=_NoCustomerMeta())
        self.log_error = patch.object(print_log.frappe, "log_error").start()
        self.addCleanup(patch.stopall)

        for patcher in (new_doc, commit, rollback, db_get_value, get_meta):
            patcher.start()

    def _commit(self) -> None:
        self.commits += 1

    def set_request(self, **values: Any) -> None:
        frappe.local.form_dict = frappe._dict(values)
        self.addCleanup(lambda: setattr(frappe.local, "form_dict", frappe._dict()))


class _NoCustomerMeta:
    def has_field(self, fieldname: str) -> bool:
        return False


class TestRegisterPrint(RecorderHarness):
    def test_a_preview_render_is_not_recorded(self) -> None:
        self.set_request()

        print_log.register_print(FakeDocument({"doctype": "Sales Order", "name": "SAL-ORD-0001"}))

        self.assertEqual(self.inserted, [])

    def test_the_print_button_is_recorded(self) -> None:
        self.set_request(trigger_print="1", format="Sales Order")

        print_log.register_print(FakeDocument({"doctype": "Sales Order", "name": "SAL-ORD-0001"}))

        self.assertEqual(len(self.inserted), 1)
        row = self.inserted[0]
        self.assertEqual(row["reference_doctype"], "Sales Order")
        self.assertEqual(row["reference_name"], "SAL-ORD-0001")
        self.assertEqual(row["channel"], print_log.CHANNEL_PRINT)
        self.assertEqual(row["print_format"], "Sales Order")

    def test_resolved_copies_are_recorded(self) -> None:
        self.set_request(trigger_print="1", format="Tax Invoice Delivery Note and Invoice")
        context = {
            "language": "Thai",
            "copies": [
                {"kind": "original", "label": "ต้นฉบับ (สำหรับลูกค้า)"},
                {"kind": "accounting", "label": "สำเนา (สำหรับฝ่ายบัญชี)"},
            ],
        }

        print_log.register_print(
            FakeDocument({"doctype": "Sales Invoice", "name": "ACC-SINV-0001", "customer": "CUST-0001"}),
            "tax_invoice",
            context,
        )

        row = self.inserted[0]
        self.assertEqual(row["copies"], 2)
        self.assertEqual(row["copy_labels"], "ต้นฉบับ (สำหรับลูกค้า), สำเนา (สำหรับฝ่ายบัญชี)")
        self.assertEqual(row["language"], "Thai")
        self.assertEqual(row["customer"], "CUST-0001")

    def test_register_print_returns_an_empty_string_for_inline_use(self) -> None:
        self.set_request(trigger_print="1")

        result = print_log.register_print(FakeDocument({"doctype": "Sales Order", "name": "SAL-ORD-0001"}))

        self.assertEqual(result, "")

    def test_quotation_customer_is_only_taken_from_a_customer_quotation(self) -> None:
        self.set_request(trigger_print="1")

        print_log.register_print(
            FakeDocument(
                {
                    "doctype": "Quotation",
                    "name": "SAL-QTN-0001",
                    "quotation_to": "Lead",
                    "party_name": "LEAD-0001",
                }
            )
        )

        self.assertIsNone(self.inserted[0]["customer"])

    def test_quotation_signatory_audit_values_are_recorded(self) -> None:
        self.set_request(trigger_print="1", format="Quotation")

        print_log.register_print(
            FakeDocument(
                {
                    "doctype": "Quotation",
                    "name": "SAL-QTN-0001",
                    "quotation_to": "Customer",
                    "party_name": "CUST-0001",
                }
            ),
            "quotation",
            {
                "show_date": False,
                "quotation_signatory_type": "Managing Director",
                "signatory": {"employee": "EMP-MANAGER"},
                "copies": [{"kind": "original", "label": "ต้นฉบับ"}],
            },
        )

        row = self.inserted[0]
        self.assertEqual(row["show_date"], 0)
        self.assertEqual(row["signatory_type"], "Managing Director")
        self.assertEqual(row["signatory_employee"], "EMP-MANAGER")


class TestRecordPrintFailsOpen(RecorderHarness):
    def test_an_insert_failure_is_logged_and_swallowed(self) -> None:
        self.log.insert.side_effect = RuntimeError("table is missing")

        print_log.record_print("Sales Invoice", "ACC-SINV-0001", print_log.CHANNEL_PDF)

        self.log_error.assert_called_once()
        message = self.log_error.call_args.kwargs["message"]
        self.assertIn("ACC-SINV-0001", message)
        self.assertIn("PDF", message)

    def test_an_empty_reference_is_ignored(self) -> None:
        print_log.record_print("", "", print_log.CHANNEL_PDF)

        self.assertEqual(self.inserted, [])
        self.log_error.assert_not_called()

    def test_a_successful_insert_commits(self) -> None:
        print_log.record_print("Sales Invoice", "ACC-SINV-0001", print_log.CHANNEL_PDF)

        self.log.insert.assert_called_once_with(ignore_permissions=True)
        self.assertEqual(self.commits, 1)


class TestDownloadPdfOverride(UnitTestCase):
    def test_the_override_matches_the_frappe_signature(self) -> None:
        from frappe.utils.print_format import download_pdf as frappe_download_pdf

        self.assertEqual(
            list(inspect.signature(print_log.download_pdf).parameters),
            list(inspect.signature(frappe_download_pdf).parameters),
        )

    def test_the_override_stays_guest_accessible(self) -> None:
        """The original allows guests; dropping that would break guest PDF links."""
        from frappe.utils.print_format import download_pdf as frappe_download_pdf

        self.assertIn(frappe_download_pdf, frappe.guest_methods)
        self.assertIn(print_log.download_pdf, frappe.whitelisted)
        self.assertIn(print_log.download_pdf, frappe.guest_methods)

    def test_the_override_returns_what_frappe_returns_and_records_it(self) -> None:
        with (
            patch("frappe.utils.print_format.download_pdf", return_value="pdf-bytes") as mocked_download,
            patch.object(print_log, "record_print") as mocked_record,
        ):
            result = print_log.download_pdf("Sales Invoice", "ACC-SINV-0001", format="Receipt")

        self.assertEqual(result, "pdf-bytes")
        mocked_download.assert_called_once()
        mocked_record.assert_called_once_with(
            "Sales Invoice",
            "ACC-SINV-0001",
            print_log.CHANNEL_PDF,
            print_format="Receipt",
            language=None,
        )

    def test_pdf_audit_values_are_forwarded_to_the_log(self) -> None:
        with (
            patch("frappe.utils.print_format.download_pdf", return_value="pdf-bytes"),
            patch.object(
                print_log,
                "_request_audit_values",
                return_value={
                    "show_date": 1,
                    "signatory_type": "Sales Representative",
                    "signatory_employee": "EMP-0001",
                },
            ),
            patch.object(print_log, "record_print") as mocked_record,
        ):
            print_log.download_pdf("Quotation", "SAL-QTN-0001", format="Quotation")

        self.assertEqual(
            mocked_record.call_args.kwargs,
            {
                "print_format": "Quotation",
                "language": None,
                "show_date": 1,
                "signatory_type": "Sales Representative",
                "signatory_employee": "EMP-0001",
            },
        )

    def test_hooks_route_the_pdf_download_through_this_module(self) -> None:
        from connect_diagnostics_core import hooks

        self.assertEqual(
            hooks.override_whitelisted_methods["frappe.utils.print_format.download_pdf"],
            "connect_diagnostics_core.api.frappe.print_log.download_pdf",
        )

    def test_register_print_is_exposed_to_jinja(self) -> None:
        from connect_diagnostics_core import hooks

        self.assertIn(
            "connect_diagnostics_core.api.frappe.print_log.register_print",
            hooks.jinja["methods"],
        )
