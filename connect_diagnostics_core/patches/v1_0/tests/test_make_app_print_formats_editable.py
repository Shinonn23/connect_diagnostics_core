# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import make_app_print_formats_editable


class TestMakeAppPrintFormatsEditable(UnitTestCase):
    @patch.object(make_app_print_formats_editable.frappe.db, "set_value")
    @patch.object(make_app_print_formats_editable.frappe, "get_all")
    def test_execute_marks_existing_app_formats_as_editable(
        self,
        mocked_get_all: MagicMock,
        mocked_set_value: MagicMock,
    ) -> None:
        mocked_get_all.return_value = ["Quotation", "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ"]

        make_app_print_formats_editable.execute()

        mocked_get_all.assert_called_once_with(
            "Print Format",
            filters={"module": "Connect Diagnostics Core", "standard": "Yes"},
            pluck="name",
        )
        self.assertEqual(
            mocked_set_value.call_args_list,
            [
                call("Print Format", "Quotation", "standard", "No", update_modified=False),
                call(
                    "Print Format",
                    "ใบกำกับภาษี ใบแจ้งหนี้ ใบส่งของ",
                    "standard",
                    "No",
                    update_modified=False,
                ),
            ],
        )
