# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from unittest.mock import MagicMock, call, patch
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from connect_diagnostics_core.setup import procure_to_pay


class TestProcureToPayPropertySetters(UnitTestCase):
    def test_purchase_order_supplier_selection_fields_are_context_only(self) -> None:
        fields = procure_to_pay.CUSTOM_FIELDS["Purchase Order"]
        reason = next(field for field in fields if field["fieldname"] == "supplier_selection_reason")
        evidence = next(field for field in fields if field["fieldname"] == "supplier_selection_evidence")
        self.assertEqual(reason["fieldtype"], "Small Text")
        self.assertEqual(reason["insert_after"], "p2p_exception_reason")
        self.assertEqual(evidence["fieldtype"], "Attach")
        self.assertEqual(evidence["insert_after"], "supplier_selection_reason")
        self.assertEqual(reason["no_copy"], 1)
        self.assertEqual(evidence["no_copy"], 1)
        self.assertFalse({"read_only", "permlevel", "roles"} & (reason.keys() | evidence.keys()))

    def test_configuration_does_not_assign_employee_roles(self) -> None:
        with (
            patch.object(procure_to_pay, "ensure_roles") as roles,
            patch.object(procure_to_pay, "assign_role_holders") as assign,
            patch.object(procure_to_pay, "activate_standard_permissions") as permissions,
            patch.object(procure_to_pay.frappe, "clear_cache") as clear_cache,
        ):
            procure_to_pay.ensure_configuration()
        roles.assert_called_once_with()
        permissions.assert_called_once_with()
        assign.assert_not_called()
        self.assertEqual(clear_cache.call_count, len(procure_to_pay.CACHE_CLEAR_DOCTYPES))

    def test_master_preflight_refuses_excess_rights_before_any_write(self) -> None:
        for target in ("Supplier", "Item", "Account"):
            for invalid in (
                {"permlevel": 1, "read": 1},
                {"if_owner": 1, "read": 1},
                {"read": 1, "write": 1},
                {"read": 1, "create": 1},
                {"read": 1, "submit": 1},
                {"read": 1, "share": 1},
                {"read": 1} if target == "Account" else {"select": 1},
            ):
                with self.subTest(target=target, invalid=invalid):
                    row = frappe._dict(invalid)

                    def rows(_table: str, *, filters: dict[str, str], **_kwargs: object) -> list[object]:
                        return [row] if filters["parent"] == target else []

                    with (
                        patch.object(procure_to_pay.frappe, "get_all", side_effect=rows),
                        patch.object(procure_to_pay, "setup_custom_perms") as copy_native,
                        patch.object(procure_to_pay, "_ensure_permission") as grant,
                        self.assertRaises(frappe.ValidationError),
                    ):
                        procure_to_pay.activate_standard_permissions()
                    copy_native.assert_not_called()
                    grant.assert_not_called()

    def test_master_copy_precedes_exact_grant_and_is_idempotent(self) -> None:
        exact = {
            "Supplier": frappe._dict({"permlevel": 0, "if_owner": 0, "read": 1}),
            "Item": frappe._dict({"permlevel": 0, "if_owner": 0, "read": 1}),
            "Account": frappe._dict({"permlevel": 0, "if_owner": 0, "select": 1}),
        }

        def rows(table: str, *, filters: dict[str, str], **_kwargs: object) -> list[object]:
            return [exact[filters["parent"]]] if table == "Custom DocPerm" else []

        with (
            patch.object(procure_to_pay.frappe, "get_all", side_effect=rows),
            patch.object(procure_to_pay, "setup_custom_perms", return_value=False) as copy_native,
            patch.object(procure_to_pay, "_ensure_material_request_permission"),
            patch.object(procure_to_pay, "_ensure_permission") as grant,
        ):
            operations = MagicMock()
            operations.attach_mock(copy_native, "copy_native")
            operations.attach_mock(grant, "grant")
            procure_to_pay.activate_standard_permissions()
            procure_to_pay.activate_standard_permissions()
        for doctype, right in (("Supplier", "read"), ("Item", "read"), ("Account", "select")):
            expected = {permission: 0 for permission in procure_to_pay.std_rights}
            expected[right] = 1
            self.assertEqual(copy_native.call_args_list.count(call(doctype)), 2)
            self.assertEqual(grant.call_args_list.count(call(doctype, "C-Level Approver", **expected)), 2)
            self.assertNotIn(call(doctype, "C-Level Approver", read=1, write=1), grant.call_args_list)
            copy_positions = [
                i for i, event in enumerate(operations.mock_calls) if event == call.copy_native(doctype)
            ]
            grant_positions = [
                i
                for i, event in enumerate(operations.mock_calls)
                if event == call.grant(doctype, "C-Level Approver", **expected)
            ]
            self.assertEqual(len(copy_positions), 2)
            self.assertTrue(
                all(copy < grant for copy, grant in zip(copy_positions, grant_positions, strict=True))
            )

    @patch.object(procure_to_pay, "_preflight_master_read_permissions")
    @patch.object(procure_to_pay, "_ensure_permission")
    @patch.object(procure_to_pay, "_ensure_material_request_permission")
    @patch.object(procure_to_pay, "setup_custom_perms", return_value=False)
    def test_c_level_approver_gets_only_purchase_order_review_rights(
        self,
        setup_custom_perms: MagicMock,
        _ensure_material_request_permission: MagicMock,
        ensure_permission: MagicMock,
        _supplier_preflight: MagicMock,
    ) -> None:
        procure_to_pay.activate_standard_permissions()

        setup_custom_perms.assert_any_call("Purchase Order")
        ensure_permission.assert_any_call(
            "Purchase Order",
            procure_to_pay.C_LEVEL_APPROVER_ROLE,
            read=1,
            write=1,
        )
        po_call = next(
            call
            for call in ensure_permission.call_args_list
            if call.args[:2] == ("Purchase Order", procure_to_pay.C_LEVEL_APPROVER_ROLE)
        )
        self.assertNotIn("submit", po_call.kwargs)
        self.assertNotIn("cancel", po_call.kwargs)

    def test_demo_and_loan_are_separate_usage_options(self) -> None:
        usage = next(
            field
            for field in procure_to_pay.CUSTOM_FIELDS["Material Request"]
            if field["fieldname"] == "request_usage"
        )

        options = str(usage["options"]).splitlines()
        self.assertIn("Customer Demo", options)
        self.assertIn("Customer Loan", options)
        self.assertNotIn("Customer Demo / Loan", options)

    def test_fulfillment_cost_fields_are_accounts_permission_level(self) -> None:
        fields = procure_to_pay.CUSTOM_FIELDS["Material Request Item"]

        self.assertEqual(
            {field["fieldname"] for field in fields},
            {"fulfillment_route", "allocated_asset", "unit_cost_ex_vat", "cost_source"},
        )
        self.assertTrue(all(field["allow_on_submit"] == 1 for field in fields))
        self.assertTrue(all(field["permlevel"] == 1 for field in fields))

    def test_purchase_reason_keeps_fieldname_with_new_label(self) -> None:
        field = next(
            field
            for field in procure_to_pay.CUSTOM_FIELDS["Material Request"]
            if field["fieldname"] == "purchase_reason"
        )

        self.assertEqual(field["label"], "Request Reason")

    def test_demo_low_value_threshold_is_company_configured(self) -> None:
        field = next(
            field
            for field in procure_to_pay.CUSTOM_FIELDS["Company"]
            if field["fieldname"] == "demo_low_value_asset_threshold"
        )

        self.assertEqual(field["fieldtype"], "Currency")
        self.assertNotIn("default", field)

    def test_purchase_order_item_list_columns_are_code_managed(self) -> None:
        self.assertEqual(
            procure_to_pay.PROPERTY_SETTERS["Purchase Order Item"],
            [
                ("item_name", "in_list_view", "1", "Check"),
            ],
        )

    @patch.object(procure_to_pay, "_preflight_master_read_permissions")
    @patch.object(procure_to_pay, "_ensure_permission")
    @patch.object(procure_to_pay, "_ensure_material_request_permission")
    @patch.object(procure_to_pay, "setup_custom_perms", return_value=False)
    def test_sales_order_financial_approver_preserves_native_roles_and_has_minimal_rights(
        self,
        setup_custom_perms: MagicMock,
        material_request_permission: MagicMock,
        ensure_permission: MagicMock,
        _supplier_preflight: MagicMock,
    ) -> None:
        operations = MagicMock()
        operations.attach_mock(setup_custom_perms, "copy_native")
        operations.attach_mock(ensure_permission, "grant")
        procure_to_pay.activate_standard_permissions()
        copy = call.copy_native("Sales Order")
        grant = call.grant("Sales Order", "Accounts Manager", read=1, write=1)
        self.assertLess(operations.mock_calls.index(copy), operations.mock_calls.index(grant))
        self.assertEqual(
            [entry for entry in ensure_permission.call_args_list if entry.args[0] == "Sales Order"],
            [call("Sales Order", "Accounts Manager", read=1, write=1)],
        )


class TestProcureToPayRoleConfigurationIntegration(IntegrationTestCase):
    def test_configuration_twice_preserves_owned_employee_user_roles(self) -> None:
        token = uuid4().hex
        clean_user = f"_test.wf15.clean.{token}@example.com"
        requester_user = f"_test.wf15.requester.{token}@example.com"
        users = (clean_user, requester_user)
        for user in users:
            self.assertFalse(frappe.db.exists("User", user))
            self.assertFalse(frappe.db.exists("Employee", {"user_id": user}))
        company = "_Test Company"
        department = frappe.db.get_value("Department", {"company": company}, "name")
        employment_type = frappe.db.get_value("Employment Type", {}, "name")
        self.assertTrue(department and employment_type)
        for role in (procure_to_pay.C_LEVEL_APPROVER_ROLE, procure_to_pay.PURCHASE_REQUESTER_ROLE):
            self.assertTrue(frappe.db.exists("Role", role))

        savepoint = f"wf15_roles_{token}"
        frappe.db.savepoint(savepoint)
        try:
            for user, role in (
                (clean_user, procure_to_pay.C_LEVEL_APPROVER_ROLE),
                (requester_user, procure_to_pay.PURCHASE_REQUESTER_ROLE),
            ):
                frappe.get_doc(
                    {
                        "doctype": "User",
                        "email": user,
                        "first_name": user,
                        "send_welcome_email": 0,
                        "user_type": "System User",
                        "roles": [{"role": role}],
                    }
                ).insert(ignore_permissions=True)
                frappe.get_doc(
                    {
                        "doctype": "Employee",
                        "first_name": user,
                        "company": company,
                        "department": department,
                        "gender": "Female",
                        "date_of_birth": "1990-05-08",
                        "date_of_joining": "2020-01-01",
                        "status": "Active",
                        "employment_type": employment_type,
                        "user_id": user,
                        "company_email": user,
                    }
                ).insert(ignore_permissions=True)

            def role_rows() -> list[dict[str, object]]:
                return frappe.get_all(
                    "Has Role",
                    filters={"parenttype": "User", "parent": ["in", list(users)]},
                    fields=["name", "parent", "parentfield", "parenttype", "role", "idx"],
                    order_by="name",
                )

            before = role_rows()
            self.assertIn(procure_to_pay.C_LEVEL_APPROVER_ROLE, frappe.get_roles(clean_user))
            self.assertNotIn(procure_to_pay.PURCHASE_REQUESTER_ROLE, frappe.get_roles(clean_user))
            self.assertIn(procure_to_pay.PURCHASE_REQUESTER_ROLE, frappe.get_roles(requester_user))
            procure_to_pay.ensure_configuration()
            procure_to_pay.ensure_configuration()
            self.assertEqual(role_rows(), before)
            self.assertNotIn(procure_to_pay.PURCHASE_REQUESTER_ROLE, frappe.get_roles(clean_user))
            self.assertIn(procure_to_pay.PURCHASE_REQUESTER_ROLE, frappe.get_roles(requester_user))
        finally:
            frappe.db.rollback(save_point=savepoint)
            for user in users:
                frappe.clear_cache(user=user)
                self.assertFalse(frappe.db.exists("User", user))
                self.assertFalse(frappe.db.exists("Employee", {"user_id": user}))
            for doctype in procure_to_pay.CACHE_CLEAR_DOCTYPES:
                frappe.clear_cache(doctype=doctype)
