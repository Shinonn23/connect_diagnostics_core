from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import stock_borrow


class TestStockBorrowValidation(UnitTestCase):
    def test_rows_reject_duplicates(self) -> None:
        with self.assertRaises(Exception):
            stock_borrow._rows([{"stock_borrow_item": "A", "qty": 1}, {"stock_borrow_item": "A", "qty": 1}])

    def test_rows_parse_json(self) -> None:
        rows = stock_borrow._rows('[{"stock_borrow_item":"A","qty":2}]')
        self.assertEqual(rows[0]["qty"], 2)

    @patch.object(stock_borrow, "_validate_request", return_value=MagicMock())
    @patch.object(stock_borrow, "_require_stock_borrow_permission")
    @patch.object(stock_borrow.frappe.db, "get_value", return_value="SBR-1")
    def test_existing_creation_checks_read_permission(
        self,
        _get_value: MagicMock,
        require: MagicMock,
        _validate: MagicMock,
    ) -> None:
        with patch.object(stock_borrow.frappe, "get_doc", return_value=MagicMock(as_dict=lambda: {})):
            stock_borrow.create_stock_borrow("MR-1")
        require.assert_called_once_with("SBR-1", "read")

    @patch.object(stock_borrow.frappe, "get_roles", return_value=["Employee"])
    @patch.object(stock_borrow, "_require_stock_borrow_permission")
    @patch.object(stock_borrow.frappe, "has_permission", return_value=True)
    @patch.object(stock_borrow.frappe, "get_doc")
    def test_receipt_confirmation_requires_stock_role(
        self,
        get_doc: MagicMock,
        _has_permission: MagicMock,
        _require_permission: MagicMock,
        _get_roles: MagicMock,
    ) -> None:
        get_doc.return_value = frappe._dict(
            docstatus=0,
            borrow_movement_type=stock_borrow.RETURN,
            stock_borrow="SBR-1",
            borrow_receipt_confirmed_at=None,
        )

        with self.assertRaises(frappe.PermissionError):
            stock_borrow.confirm_physical_receipt("SE-1")
