# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests import UnitTestCase

from connect_diagnostics_core.patches.v1_0.add_journal_entry_approval_controls import _fields
from connect_diagnostics_core.setup.workflow_fields import CUSTOM_FIELDS


class TestJournalEntryApprovalPatch(UnitTestCase):
    def test_field_manifest_is_additive_and_deterministic(self) -> None:
        fields = _fields()["Journal Entry"]
        self.assertIs(fields, CUSTOM_FIELDS["Journal Entry"])
        self.assertEqual(fields[0]["fieldname"], "workflow_state")
        self.assertTrue(all(field["no_copy"] and field["read_only"] for field in fields[1:]))
        operation_field = next(field for field in fields if field["fieldname"] == "approval_operation_id")
        self.assertEqual(operation_field["fieldtype"], "Data")
        self.assertEqual(operation_field["hidden"], 1)
        self.assertEqual(operation_field["allow_on_submit"], 1)
        self.assertEqual(operation_field["is_system_generated"], 1)
