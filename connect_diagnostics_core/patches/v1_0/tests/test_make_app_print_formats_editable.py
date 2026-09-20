# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0 import make_app_print_formats_editable


class TestMakeAppPrintFormatsEditable(UnitTestCase):
    def test_execute_does_not_normalize_standard_flag(self) -> None:
        self.assertIsNone(make_app_print_formats_editable.execute())
