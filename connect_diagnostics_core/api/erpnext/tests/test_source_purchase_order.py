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


class TestJoinSourceCopies(UnitTestCase):
    def _doc(self, rows: list[dict[str, Any]]) -> Any:
        return frappe._dict({"source_purchase_orders": [frappe._dict(row) for row in rows]})

    def test_rows_are_appended_in_order_with_per_row_copies(self) -> None:
        doc = self._doc(
            [
                {"purchase_order": "PUR-ORD-0001", "copies": 2},
                {"purchase_order": "PUR-ORD-0002", "copies": 1},
            ]
        )
        by_order = {"PUR-ORD-0001": pdf_bytes(3), "PUR-ORD-0002": pdf_bytes(1)}
        with patch.object(
            source_purchase_order,
            "_row_pdf",
            side_effect=lambda row: by_order[row.get("purchase_order")],
        ):
            joined = source_purchase_order._join_source_copies(doc, pdf_bytes(2), default_copies=5)

        assert joined is not None
        # invoice(2) + order1 x2 (3 pages each) + order2 x1 (1 page)
        self.assertEqual(len(PdfReader(BytesIO(joined)).pages), 2 + 3 * 2 + 1)

    def test_a_blank_copy_count_falls_back_to_the_default(self) -> None:
        doc = self._doc([{"purchase_order": "PUR-ORD-0001", "copies": ""}])
        with patch.object(source_purchase_order, "_row_pdf", return_value=pdf_bytes(1)):
            joined = source_purchase_order._join_source_copies(doc, pdf_bytes(1), default_copies=3)

        assert joined is not None
        self.assertEqual(len(PdfReader(BytesIO(joined)).pages), 1 + 3)

    def test_no_appendable_rows_returns_none(self) -> None:
        doc = self._doc([{"purchase_order": "", "purchase_order_file": ""}])
        with patch.object(source_purchase_order, "_row_pdf", return_value=None):
            self.assertIsNone(source_purchase_order._join_source_copies(doc, pdf_bytes(1), default_copies=1))

    def test_row_copies_reads_the_row_and_clamps_negatives(self) -> None:
        self.assertEqual(source_purchase_order._row_copies(frappe._dict({"copies": 4}), 2), 4)
        self.assertEqual(source_purchase_order._row_copies(frappe._dict({"copies": ""}), 2), 2)
        self.assertEqual(source_purchase_order._row_copies(frappe._dict({"copies": None}), 3), 3)
        self.assertEqual(source_purchase_order._row_copies(frappe._dict({"copies": -1}), 3), 0)


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
