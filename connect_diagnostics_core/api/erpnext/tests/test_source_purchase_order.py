# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from io import BytesIO
from typing import Any
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from pypdf import PdfReader, PdfWriter

from connect_diagnostics_core.api.erpnext import source_purchase_order


def pdf_bytes(pages: int) -> bytes:
    writer = PdfWriter()
    for _page in range(pages):
        writer.add_blank_page(width=210, height=297)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class TestJoin(UnitTestCase):
    def test_each_copy_is_appended_after_the_invoice(self) -> None:
        joined = source_purchase_order._join(pdf_bytes(2), pdf_bytes(3), copies=2)

        self.assertEqual(len(PdfReader(BytesIO(joined)).pages), 2 + 3 + 3)

    def test_a_single_copy_appends_once(self) -> None:
        joined = source_purchase_order._join(pdf_bytes(1), pdf_bytes(1), copies=1)

        self.assertEqual(len(PdfReader(BytesIO(joined)).pages), 2)


class TestAttachedFile(UnitTestCase):
    def _with_content(self, content: Any) -> Any:
        document = frappe._dict({"get_content": lambda: content})
        return (
            patch.object(source_purchase_order.frappe.db, "exists", return_value=True),
            patch.object(source_purchase_order.frappe, "get_doc", return_value=document),
        )

    def test_a_pdf_attachment_is_used(self) -> None:
        content = pdf_bytes(1)
        exists, get_doc = self._with_content(content)
        with exists, get_doc:
            self.assertEqual(source_purchase_order._attached_pdf("/files/po.pdf"), content)

    def test_an_image_attachment_is_skipped(self) -> None:
        """A scanned order uploaded as an image cannot be concatenated."""
        exists, get_doc = self._with_content(b"\x89PNG\r\n\x1a\n")
        with exists, get_doc:
            self.assertIsNone(source_purchase_order._attached_pdf("/files/po.png"))

    def test_a_missing_file_is_skipped(self) -> None:
        with patch.object(source_purchase_order.frappe.db, "exists", return_value=False):
            self.assertIsNone(source_purchase_order._attached_pdf("/files/gone.pdf"))


class TestResponseGuard(UnitTestCase):
    def test_a_non_pdf_response_is_left_alone(self) -> None:
        with patch.object(
            source_purchase_order.frappe, "local", frappe._dict({"response": frappe._dict({"type": "csv"})})
        ):
            self.assertIsNone(source_purchase_order._response_pdf())

    def test_a_pdf_response_is_returned(self) -> None:
        content = pdf_bytes(1)
        response = frappe._dict({"type": "pdf", "filecontent": content})
        with patch.object(source_purchase_order.frappe, "local", frappe._dict({"response": response})):
            self.assertEqual(source_purchase_order._response_pdf(), content)


class TestFailOpen(UnitTestCase):
    def test_a_failure_never_blocks_the_invoice(self) -> None:
        """The Customer must still get their invoice when the copy cannot be built."""
        with (
            patch.object(
                source_purchase_order,
                "_append_source_copy",
                side_effect=RuntimeError("wkhtmltopdf died"),
            ),
            patch.object(source_purchase_order.frappe, "log_error") as mocked_log,
        ):
            source_purchase_order.append_source_copy(
                "Sales Invoice", "ACC-SINV-0001", "Tax Invoice Delivery Note and Invoice"
            )

        mocked_log.assert_called_once()

    def test_an_unrelated_print_format_is_ignored(self) -> None:
        with patch.object(source_purchase_order, "_response_pdf") as mocked_response:
            source_purchase_order._append_source_copy("Sales Order", "SAL-ORD-0001", "Sales Order")

        mocked_response.assert_not_called()
