from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext import item


class TestItemBorrowValidation(UnitTestCase):
    @patch.object(item.regulatory, "validate_item_classification")
    def test_non_stock_borrow_item_is_rejected(self, validate_classification: MagicMock) -> None:
        doc = MagicMock()
        doc.get.side_effect = lambda key: {"allow_borrow": 1, "is_stock_item": 0}.get(key)
        with self.assertRaises(Exception):
            item.validate(doc, "validate")
        validate_classification.assert_not_called()
