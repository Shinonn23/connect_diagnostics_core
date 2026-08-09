# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from unittest.mock import patch

from frappe.tests import UnitTestCase

from connect_diagnostics_core.api.erpnext.regulatory_import import validate_regulatory_import_rows


class TestRegulatoryImport(UnitTestCase):
    def test_preflight_detects_normalized_duplicate_registration_numbers(self) -> None:
        rows = json.dumps(
            [{"registration_number": "68-2-2-1-0006254"}, {"registration_number": "682210006254"}]
        )
        with patch(
            "connect_diagnostics_core.api.erpnext.regulatory_import.frappe.has_permission", return_value=True
        ):
            result = validate_regulatory_import_rows(rows)

        self.assertFalse(result["data"]["valid"])
        self.assertEqual(result["data"]["errors"][0]["row"], 2)
