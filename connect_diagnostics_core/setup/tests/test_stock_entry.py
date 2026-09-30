from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import stock_entry


class TestStockEntryFields(UnitTestCase):
    def test_borrow_fields_are_declared(self) -> None:
        fields = {field["fieldname"]: field for field in stock_entry.CUSTOM_FIELDS["Stock Entry"]}
        self.assertEqual(fields["stock_borrow"]["options"], "Stock Borrow")
        self.assertEqual(fields["borrow_movement_type"]["options"], "Borrow Outbound\nBorrow Exact Return")
        detail_fields = {
            field["fieldname"]: field for field in stock_entry.CUSTOM_FIELDS["Stock Entry Detail"]
        }
        self.assertEqual(detail_fields["stock_borrow_item"]["options"], "Stock Borrow Item")
