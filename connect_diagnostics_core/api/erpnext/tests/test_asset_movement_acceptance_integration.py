# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch
from uuid import uuid4

import frappe
from erpnext.assets.doctype.asset.test_asset import create_asset
from frappe import client
from frappe.model.document import Document, copy_doc
from frappe.model.workflow import apply_workflow
from frappe.tests import IntegrationTestCase
from frappe.utils.background_jobs import get_jobs
from frappe.utils.scheduler import is_scheduler_disabled

from connect_diagnostics_core.api.erpnext import asset_installation
from connect_diagnostics_core.api.erpnext import asset_movement_acceptance as acceptance
from connect_diagnostics_core.api.erpnext import asset_movement_workflow as workflow
from connect_diagnostics_core.api.erpnext.tests import test_asset_movement_workflow as fixtures


class TestAssetMovementAcceptanceIntegration(IntegrationTestCase):
    _actor = fixtures.TestAssetMovementWorkflowIntegration._actor
    _location = fixtures.TestAssetMovementWorkflowIntegration._location
    _asset = fixtures.TestAssetMovementWorkflowIntegration._asset

    def _assert_denied(self, action: Callable[[], object]) -> None:
        savepoint = f"asset_terminal_denial_{uuid4().hex}"
        frappe.db.savepoint(savepoint)
        try:
            with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
                action()
        finally:
            frappe.db.rollback(save_point=savepoint)
            frappe.clear_cache(doctype="Asset Movement")

    def setUp(self) -> None:
        super().setUp()
        user = frappe.session.user
        request = getattr(frappe.local, "request", None)
        grants = getattr(frappe.local, "_connect_diagnostics_approval_field_grants", None)
        old_grants = list(grants) if grants is not None else None

        def restore() -> None:
            frappe.set_user(user)
            frappe.local.request = request
            if old_grants is None:
                if hasattr(frappe.local, "_connect_diagnostics_approval_field_grants"):
                    delattr(frappe.local, "_connect_diagnostics_approval_field_grants")
            else:
                frappe.local._connect_diagnostics_approval_field_grants = old_grants
            for actor in getattr(self, "actors", ()):
                frappe.clear_cache(user=actor)

        self.addCleanup(restore)
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user("Administrator")
        self.actors: list[str] = []
        self.employees: list[str] = []
        for label, role in (
            ("maker", workflow.MAKER_ROLE),
            ("reviewer", workflow.REVIEWER_ROLE),
            ("approver", workflow.APPROVER_ROLE),
            ("receiver", workflow.MAKER_ROLE),
        ):
            with patch("frappe.core.doctype.user.user.throttle_user_creation"):
                actor, employee = self._actor(
                    f"_test.asset.receipt.{label}.{uuid4().hex}@example.com",
                    role,
                    signature="data:image/svg+xml;base64,PHN2Zy8+",
                )
            self.actors.append(actor)
            self.employees.append(employee)
        self.maker, self.reviewer, self.approver, self.receiver = self.actors
        self.source = self._location("Receipt Source")
        self.target = self._location("Receipt Target")
        self.assets = [self._asset(self.source), self._asset(self.source)]
        for asset in self.assets:
            asset.make_asset_movement()
        print_patcher = patch("frappe.attach_print", return_value={})
        print_patcher.start()
        self.addCleanup(print_patcher.stop)

    def _draft(self, *, employee: bool = False) -> Document:
        frappe.set_user(self.maker)
        return frappe.get_doc(
            {
                "doctype": "Asset Movement",
                "company": "_Test Company",
                "purpose": "Transfer",
                "transaction_date": frappe.utils.now(),
                "assets": [
                    {
                        "asset": asset.name,
                        "company": asset.company,
                        "source_location": self.source,
                        "target_location": self.target,
                        "receiver_user": self.receiver if employee or index == 0 else self.approver,
                        "to_employee": self.employees[-1] if employee else None,
                    }
                    for index, asset in enumerate(self.assets)
                ],
            }
        ).insert()

    def _submit(self, *, employee: bool = False) -> Document:
        doc = self._draft(employee=employee)
        for actor, action in (
            (self.maker, "Send Asset Movement for Review"),
            (self.reviewer, "Review Asset Movement"),
            (self.approver, "Approve Asset Movement"),
            (self.reviewer, "Submit Asset Movement"),
        ):
            frappe.set_user(actor)
            doc = apply_workflow(doc, action)
        return doc.reload()

    def _native_receipt(self, asset_name: str) -> Document:
        name = frappe.db.get_value(
            "Asset Movement",
            [["Asset Movement Item", "asset", "=", asset_name], ["purpose", "=", "Receipt"]],
            "name",
            order_by="creation desc",
        )
        assert name
        return frappe.get_doc("Asset Movement", name)

    def test_installation_customer_follows_native_receipt_and_cancellation(self) -> None:
        customer_name = f"_Test Installation Customer {uuid4().hex[:8]}"
        frappe.set_user("Administrator")
        self.assertTrue(frappe.db.exists("Item", "Macbook Pro"))
        self.assertTrue(frappe.db.exists("Asset Category", "Computers"))
        frappe.get_doc(
            {
                "doctype": "Customer",
                "name": customer_name,
                "customer_name": customer_name,
                "customer_type": "Company",
                "customer_group": "All Customer Groups",
                "territory": "All Territories",
            }
        ).db_insert()
        asset = create_asset(
            asset_name=f"_Test Installed Asset {uuid4().hex}",
            item_code="Macbook Pro",
            asset_category="Computers",
            company="_Test Company",
            asset_type="Existing Asset",
            location=self.source,
            purchase_date=frappe.utils.today(),
            available_for_use_date=frappe.utils.today(),
            calculate_depreciation=0,
        )
        asset.submit()
        frappe.set_user(self.maker)
        doc = frappe.get_doc(
            {
                "doctype": "Asset Movement",
                "company": "_Test Company",
                "purpose": "Transfer",
                "transaction_date": frappe.utils.now(),
                "assets": [
                    {
                        "asset": asset.name,
                        "company": "_Test Company",
                        "source_location": self.source,
                        "target_location": self.target,
                        "to_employee": self.employees[-1],
                        "receiver_user": self.receiver,
                        "installation_customer": customer_name,
                    }
                ],
            }
        ).insert()
        for actor, action in (
            (self.maker, "Send Asset Movement for Review"),
            (self.reviewer, "Review Asset Movement"),
            (self.approver, "Approve Asset Movement"),
            (self.reviewer, "Submit Asset Movement"),
        ):
            frappe.set_user(actor)
            doc = apply_workflow(doc, action)
        row = doc.get("assets")[0]
        self.assertEqual(row.installation_previous_customer, None)
        self.assertFalse(frappe.db.get_value("Asset", row.asset, "customer"))
        frappe.set_user(self.receiver)
        acceptance.confirm_receipt(doc.name, row.name)
        self.assertEqual(frappe.db.get_value("Asset", row.asset, "customer"), customer_name)
        frappe.set_user(self.reviewer)
        apply_workflow(frappe.get_doc("Asset Movement", doc.name), "Cancel Asset Movement")
        self.assertFalse(frappe.db.get_value("Asset", row.asset, "customer"))

    def _receipt_actions(self, name: str) -> list[frappe._dict]:
        return frappe.get_all(
            "Workflow Action",
            {"reference_doctype": "Asset Movement", "reference_name": name},
            ["name", "workflow_state", "status"],
            order_by="creation, name",
        )

    def test_native_receipt_has_only_submitted_action_and_cancel_completes_it(self) -> None:
        asset = self.assets[0]
        receipt = self._native_receipt(str(asset.name))
        self.assertEqual(receipt.docstatus, 1)
        self.assertEqual(receipt.get("workflow_state"), workflow.STATE_SUBMITTED)
        self.assertEqual(receipt.get("purpose"), "Receipt")
        self.assertEqual(receipt.get("company"), asset.company)
        self.assertEqual(receipt.get("assets")[0].get("asset"), asset.name)
        self.assertEqual(receipt.get("assets")[0].get("target_location"), self.source)
        self.assertEqual(
            [(row.workflow_state, row.status) for row in self._receipt_actions(str(receipt.name))],
            [(workflow.STATE_SUBMITTED, "Open")],
        )
        asset.cancel_movement_entries()
        receipt.reload()
        self.assertEqual(receipt.docstatus, 2)
        self.assertEqual(receipt.get("workflow_state"), workflow.STATE_CANCELLED)
        self.assertEqual(
            [(row.workflow_state, row.status) for row in self._receipt_actions(str(receipt.name))],
            [(workflow.STATE_SUBMITTED, "Completed")],
        )

    def test_native_receipt_requires_create_write_and_submit_without_leftover_effects(self) -> None:
        original_check = Document.check_permission
        for denied in ("create", "write", "submit"):
            with self.subTest(permission=denied):
                asset = self._asset(self.source)
                savepoint = f"asset_receipt_permission_{uuid4().hex}"
                frappe.db.savepoint(savepoint)
                seen: list[str] = []
                generated: list[str] = []
                action_names: list[str] = []

                def check_permission(
                    doc: Document, permtype: str = "read", permlevel: int | None = None
                ) -> None:
                    if doc.doctype == "Asset Movement":
                        seen.append(permtype)
                        if permtype == denied:
                            raise frappe.PermissionError(f"Denied {denied}")
                    original_check(doc, permtype, permlevel)

                try:
                    with (
                        patch.object(Document, "check_permission", new=check_permission),
                        self.assertRaises(frappe.PermissionError),
                    ):
                        asset.make_asset_movement()
                finally:
                    generated = frappe.get_all(
                        "Asset Movement",
                        [["Asset Movement Item", "asset", "=", asset.name], ["purpose", "=", "Receipt"]],
                        pluck="name",
                    )
                    for name in generated:
                        action_names.extend(str(row.name) for row in self._receipt_actions(str(name)))
                    frappe.db.rollback(save_point=savepoint)
                self.assertIn(denied, seen)
                self.assertFalse(
                    frappe.db.get_value(
                        "Asset Movement",
                        [["Asset Movement Item", "asset", "=", asset.name], ["purpose", "=", "Receipt"]],
                        "name",
                    )
                )
                for name in generated:
                    self.assertFalse(frappe.db.exists("Asset Movement", name))
                for name in action_names:
                    self.assertFalse(frappe.db.exists("Workflow Action", name))
                self.assertEqual(frappe.db.get_value("Asset", asset.name, "location"), self.source)

    def test_actual_asset_submit_creates_terminal_receipt_action(self) -> None:
        if not (frappe.db.exists("Item", "Macbook Pro") and frappe.db.exists("Asset Category", "Computers")):
            self.skipTest("ERPNext fixed Asset item/category fixture is unavailable")
        asset = create_asset(
            asset_name=f"_Test Native Asset Receipt {uuid4().hex}",
            item_code="Macbook Pro",
            asset_category="Computers",
            location=self.source,
            purchase_date=frappe.utils.today(),
            available_for_use_date=frappe.utils.today(),
            calculate_depreciation=0,
        )
        asset.submit()
        receipt = self._native_receipt(str(asset.name))
        self.assertEqual(receipt.docstatus, 1)
        self.assertEqual(receipt.get("workflow_state"), workflow.STATE_SUBMITTED)
        self.assertEqual(
            [(row.workflow_state, row.status) for row in self._receipt_actions(str(receipt.name))],
            [(workflow.STATE_SUBMITTED, "Open")],
        )

    def test_terminal_state_forgery_preserves_assets_and_receiver_handoff(self) -> None:
        doc = self._draft(employee=True)
        for actor, action in (
            (self.maker, "Send Asset Movement for Review"),
            (self.reviewer, "Review Asset Movement"),
            (self.approver, "Approve Asset Movement"),
        ):
            frappe.set_user(actor)
            doc = apply_workflow(doc, action)
        doc.reload()
        approval = (
            doc.get("approval_maker_user"),
            doc.get("approval_reviewer_user"),
            doc.get("approval_approver_user"),
            doc.get("approval_critical_digest"),
        )
        before_assets = [
            frappe.db.get_value("Asset", asset.name, ["location", "custodian"]) for asset in self.assets
        ]
        frappe.set_user(self.reviewer)

        def fake_submit(*, api: bool) -> object:
            candidate = frappe.get_doc("Asset Movement", doc.name)
            candidate.set("workflow_state", workflow.STATE_SUBMITTED)
            if api:
                return client.save(frappe.as_json(candidate.as_dict()))
            return candidate.save()

        with patch.object(
            workflow.approval_controls,
            "require_native_terminal_state",
            wraps=workflow.approval_controls.require_native_terminal_state,
        ) as guard:
            self._assert_denied(lambda: fake_submit(api=False))
            guard.assert_called()
        with patch.object(
            workflow.approval_controls,
            "require_native_terminal_state",
            wraps=workflow.approval_controls.require_native_terminal_state,
        ) as guard:
            self._assert_denied(lambda: fake_submit(api=True))
            guard.assert_called()
        with patch.object(
            workflow.approval_controls,
            "require_native_terminal_state",
            wraps=workflow.approval_controls.require_native_terminal_state,
        ) as guard:
            self._assert_denied(
                lambda: client.set_value(
                    "Asset Movement", doc.name, "workflow_state", workflow.STATE_SUBMITTED
                )
            )
            guard.assert_called()
        doc.reload()
        self.assertEqual(doc.docstatus, 0)
        self.assertEqual(doc.get("workflow_state"), workflow.STATE_APPROVED)
        self.assertEqual(
            (
                doc.get("approval_maker_user"),
                doc.get("approval_reviewer_user"),
                doc.get("approval_approver_user"),
                doc.get("approval_critical_digest"),
            ),
            approval,
        )
        self.assertTrue(all(not row.accepted_by for row in doc.get("assets")))
        self.assertEqual(
            [frappe.db.get_value("Asset", asset.name, ["location", "custodian"]) for asset in self.assets],
            before_assets,
        )
        doc = apply_workflow(doc, "Submit Asset Movement")
        doc.reload()
        self.assertEqual(doc.docstatus, 1)
        submitted_assets = [
            frappe.db.get_value("Asset", asset.name, ["location", "custodian"]) for asset in self.assets
        ]

        def fake_cancel(*, api: bool) -> object:
            candidate = frappe.get_doc("Asset Movement", doc.name)
            candidate.set("workflow_state", workflow.STATE_CANCELLED)
            if api:
                return client.save(frappe.as_json(candidate.as_dict()))
            return candidate.save()

        with patch.object(
            workflow.approval_controls,
            "require_locked_submitted_update",
            wraps=workflow.approval_controls.require_locked_submitted_update,
        ) as guard:
            self._assert_denied(lambda: fake_cancel(api=False))
            guard.assert_called()
        with patch.object(
            workflow.approval_controls,
            "require_locked_submitted_update",
            wraps=workflow.approval_controls.require_locked_submitted_update,
        ) as guard:
            self._assert_denied(lambda: fake_cancel(api=True))
            guard.assert_called()
        with patch.object(
            workflow.approval_controls,
            "require_locked_submitted_update",
            wraps=workflow.approval_controls.require_locked_submitted_update,
        ) as guard:
            self._assert_denied(
                lambda: client.set_value(
                    "Asset Movement", doc.name, "workflow_state", workflow.STATE_CANCELLED
                )
            )
            guard.assert_called()
        doc.reload()
        self.assertEqual(doc.docstatus, 1)
        self.assertEqual(doc.get("workflow_state"), workflow.STATE_SUBMITTED)
        self.assertEqual(
            [frappe.db.get_value("Asset", asset.name, ["location", "custodian"]) for asset in self.assets],
            submitted_assets,
        )
        historical = f"asset_history_{uuid4().hex}"
        frappe.db.savepoint(historical)
        try:
            frappe.db.set_value(
                "Asset Movement", doc.name, "workflow_state", "Stock Entry Submitted", update_modified=False
            )
            legacy = frappe.get_doc("Asset Movement", doc.name)
            with patch.object(
                workflow.approval_controls,
                "require_locked_submitted_update",
                wraps=workflow.approval_controls.require_locked_submitted_update,
            ) as guard:
                with self.assertRaisesRegex(frappe.ValidationError, "not a valid Workflow State"):
                    legacy.save()
                guard.assert_not_called()
            self.assertEqual(
                frappe.db.get_value("Asset Movement", doc.name, "workflow_state"),
                "Stock Entry Submitted",
            )
            self.assertEqual(
                [
                    frappe.db.get_value("Asset", asset.name, ["location", "custodian"])
                    for asset in self.assets
                ],
                submitted_assets,
            )
        finally:
            frappe.db.rollback(save_point=historical)
            frappe.clear_cache(doctype="Asset Movement")
        doc.reload()
        frappe.set_user(self.receiver)
        acceptance.confirm_receipt(doc.name, doc.get("assets")[0].name)
        doc.reload()
        self.assertEqual(doc.get("assets")[0].accepted_by, self.receiver)
        frappe.set_user(self.reviewer)
        apply_workflow(doc, "Cancel Asset Movement")
        doc.reload()
        self.assertEqual(doc.docstatus, 2)

    def test_per_asset_confirmation_replay_cancel_and_amend(self) -> None:
        doc = self._submit()
        locations = [frappe.db.get_value("Asset", asset.name, "location") for asset in self.assets]
        self.assertEqual(locations, [self.target, self.target])
        row = doc.get("assets")[0]
        frappe.set_user(self.maker)
        with self.assertRaises(frappe.ValidationError):
            acceptance.confirm_receipt(doc.name, row.name)
        frappe.set_user(self.receiver)
        result = acceptance.confirm_receipt(doc.name, row.name)
        self.assertEqual(result["data"]["accepted_by"], self.receiver)
        self.assertEqual(acceptance.confirm_receipt(doc.name, row.name)["data"], result["data"])
        doc.reload()
        self.assertFalse(doc.get("assets")[1].accepted_by)
        with self.assertRaises(frappe.ValidationError):
            acceptance.confirm_receipt(doc.name, doc.get("assets")[1].name)
        comments = frappe.get_all(
            "Comment",
            filters={
                "reference_doctype": "Asset Movement",
                "reference_name": doc.name,
                "comment_type": "Info",
            },
            fields=["content"],
        )
        self.assertEqual(sum(row.name in comment.content for comment in comments), 1)
        self.assertEqual(
            [frappe.db.get_value("Asset", asset.name, "location") for asset in self.assets], locations
        )
        frappe.set_user(self.reviewer)
        apply_workflow(doc, "Cancel Asset Movement")
        doc.reload()
        self.assertEqual(doc.get("assets")[0].accepted_by, self.receiver)
        self.assertEqual(
            [frappe.db.get_value("Asset", asset.name, "location") for asset in self.assets],
            [self.source, self.source],
        )
        frappe.set_user(self.receiver)
        with self.assertRaises(frappe.ValidationError):
            acceptance.confirm_receipt(doc.name, row.name)
        amended = copy_doc(doc, ignore_no_copy=False)
        for child in amended.get("assets"):
            self.assertFalse(child.accepted_by)
            self.assertFalse(child.accepted_at)
            self.assertFalse(child.receiver_user)

    def test_employee_current_mapping_and_disabled_receiver_deny(self) -> None:
        doc = self._submit(employee=True)
        frappe.set_user(self.receiver)
        row = doc.get("assets")[0]
        for changes in ({"status": "Left"}, {"user_id": self.maker}):
            frappe.db.savepoint("receiver_mapping")
            try:
                frappe.db.set_value("Employee", self.employees[-1], changes)
                with self.assertRaises(frappe.ValidationError):
                    acceptance.confirm_receipt(doc.name, row.name)
                self.assertFalse(frappe.db.get_value("Asset Movement Item", row.name, "accepted_by"))
            finally:
                frappe.db.rollback(save_point="receiver_mapping")
        frappe.db.set_value("User", self.receiver, "enabled", 0)
        with self.assertRaises(frappe.ValidationError):
            acceptance.confirm_receipt(doc.name, row.name)

    def test_parent_and_standalone_child_spoof_denied(self) -> None:
        doc = self._draft()
        row = doc.get("assets")[0]
        row.accepted_by = self.receiver
        row.accepted_at = frappe.utils.now()
        with self.assertRaises(frappe.ValidationError):
            doc.save()
        doc.reload()
        with self.assertRaises(frappe.ValidationError):
            doc.get("assets")[0].save(ignore_permissions=True)
        child = frappe.get_doc(doc.get("assets")[0].as_dict())
        child.name = None
        with self.assertRaises(frappe.ValidationError):
            child.insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            frappe.delete_doc("Asset Movement Item", doc.get("assets")[0].name, ignore_permissions=True)
        doc = self._submit()
        doc.get("assets")[0].receiver_user = self.maker
        with self.assertRaises(frappe.ValidationError):
            doc.save()
        doc.reload()
        doc.get("assets")[0].accepted_by = self.receiver
        doc.get("assets")[0].accepted_at = frappe.utils.now()
        with self.assertRaises(frappe.ValidationError):
            doc.save()

    def test_confirmation_scope_wrong_parent_and_atomic_comment_failure(self) -> None:
        doc = self._submit()
        frappe.set_user(self.receiver)
        with (
            patch.object(acceptance.frappe, "has_permission", return_value=False),
            self.assertRaises(frappe.PermissionError),
        ):
            acceptance.confirm_receipt(doc.name, doc.get("assets")[0].name)
        with self.assertRaises(frappe.ValidationError):
            acceptance.confirm_receipt(doc.name, "foreign-row")
        with (
            patch.object(type(doc), "add_comment", side_effect=RuntimeError("comment failed")),
            self.assertRaises(RuntimeError),
        ):
            acceptance.confirm_receipt(doc.name, doc.get("assets")[0].name)
        self.assertFalse(frappe.db.get_value("Asset Movement Item", doc.get("assets")[0].name, "accepted_by"))
        self.assertFalse(frappe.db.get_value("Asset Movement Item", doc.get("assets")[0].name, "accepted_at"))

    def test_native_client_rpc_cannot_manufacture_receipt_or_change_submitted_receiver(self) -> None:
        doc = self._submit()
        row = doc.get("assets")[0]
        frappe.set_user(self.reviewer)
        for fieldname, value in (
            ("accepted_by", self.receiver),
            ("accepted_at", frappe.utils.now()),
            ("receiver_user", self.maker),
        ):
            with self.subTest(fieldname=fieldname), self.assertRaises(frappe.ValidationError):
                client.set_value("Asset Movement Item", row.name, fieldname, value)
        payload = doc.as_dict()
        payload["assets"][0]["accepted_by"] = self.receiver
        payload["assets"][0]["accepted_at"] = frappe.utils.now()
        with self.assertRaises(frappe.ValidationError):
            client.set_value("Asset Movement", doc.name, {"assets": payload["assets"]})
        with self.assertRaises(frappe.ValidationError):
            client.save(payload)
        with self.assertRaises(frappe.ValidationError):
            client.save(row.as_dict())
        child_payload = row.as_dict()
        child_payload["name"] = None
        child_payload["accepted_by"] = self.receiver
        with self.assertRaises(frappe.ValidationError):
            client.insert(child_payload)
        with self.assertRaises(frappe.ValidationError):
            client.delete("Asset Movement Item", row.name)
        doc.reload()
        self.assertFalse(doc.get("assets")[0].accepted_by)
        self.assertFalse(doc.get("assets")[0].accepted_at)
        self.assertEqual(doc.get("assets")[0].receiver_user, self.receiver)

    def test_missing_receiver_denied_before_approval_and_receiver_digest_bound(self) -> None:
        doc = self._draft()
        doc.get("assets")[0].receiver_user = None
        doc.save()
        with self.assertRaises(frappe.ValidationError):
            apply_workflow(doc, "Send Asset Movement for Review")
        doc.reload()
        doc.get("assets")[0].receiver_user = self.receiver
        doc.save()
        doc = apply_workflow(doc, "Send Asset Movement for Review")
        doc.get("assets")[0].receiver_user = self.reviewer
        with self.assertRaises(frappe.ValidationError):
            doc.save()


class TestAssetInstallationConcurrencyIntegration(IntegrationTestCase):
    """Commit only exact owned native history needed by two DB connections."""

    _actor = fixtures.TestAssetMovementWorkflowIntegration._actor
    _location = fixtures.TestAssetMovementWorkflowIntegration._location

    def setUp(self) -> None:
        super().setUp()
        self.assertTrue(frappe.in_test)
        self.assertTrue(is_scheduler_disabled(verbose=False))
        original_user = frappe.session.user
        original_request = getattr(frappe.local, "request", None)
        self.addCleanup(frappe.set_user, original_user)
        self.addCleanup(setattr, frappe.local, "request", original_request)
        patcher = patch("frappe.attach_print", return_value={})
        patcher.start()
        self.addCleanup(patcher.stop)
        frappe.local.request = frappe._dict(method="POST")
        frappe.set_user("Administrator")
        self.owned: dict[str, str] = {}
        self._committed = False
        self.addCleanup(self._close_owned_history)
        suffix = uuid4().hex
        actors: list[str] = []
        employees: list[str] = []
        for label, role in (
            ("maker", workflow.MAKER_ROLE),
            ("reviewer", workflow.REVIEWER_ROLE),
            ("approver", workflow.APPROVER_ROLE),
            ("receiver", workflow.MAKER_ROLE),
        ):
            with patch("frappe.core.doctype.user.user.throttle_user_creation"):
                actor, employee = self._actor(
                    f"_test.asset.install.{label}.{suffix}@example.com",
                    role,
                    signature="data:image/svg+xml;base64,PHN2Zy8+",
                )
            actors.append(actor)
            employees.append(employee)
            self.owned[f"{label}_user"] = actor
            self.owned[f"{label}_employee"] = employee
        self.maker, self.reviewer, self.approver, self.receiver = actors
        self.receiver_employee = employees[-1]
        self.source = self._location(f"Install Source {suffix}")
        self.target = self._location(f"Install Target {suffix}")
        self.owned.update(source=self.source, target=self.target)
        self.assertTrue(frappe.db.exists("Item", "Macbook Pro"))
        self.assertTrue(frappe.db.exists("Asset Category", "Computers"))
        asset = create_asset(
            asset_name=f"_Test Native Installation Asset {suffix}",
            item_code="Macbook Pro",
            asset_category="Computers",
            company="_Test Company",
            asset_type="Existing Asset",
            location=self.source,
            purchase_date=frappe.utils.today(),
            available_for_use_date=frappe.utils.today(),
            calculate_depreciation=0,
        )
        asset.submit()
        self.owned["asset"] = str(asset.name)
        receipt = frappe.db.get_value(
            "Asset Movement",
            [["Asset Movement Item", "asset", "=", asset.name], ["purpose", "=", "Receipt"]],
            "name",
            order_by="creation desc",
        )
        assert receipt
        self.owned["receipt"] = str(receipt)
        for index in (1, 2):
            name = f"_Test Installation Customer {index} {suffix}"
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "name": name,
                    "customer_name": name,
                    "customer_type": "Company",
                    "customer_group": "All Customer Groups",
                    "territory": "All Territories",
                }
            ).db_insert()
            self.owned[f"customer_{index}"] = name

    def _approve(self, doc: Document) -> Document:
        for actor, action in (
            (self.maker, "Send Asset Movement for Review"),
            (self.reviewer, "Review Asset Movement"),
            (self.approver, "Approve Asset Movement"),
            (self.reviewer, "Submit Asset Movement"),
        ):
            frappe.set_user(actor)
            doc = apply_workflow(doc, action)
        return doc.reload()

    def _install(self, source: str, target: str, customer: str, from_employee: str | None) -> Document:
        frappe.set_user(self.maker)
        doc = frappe.get_doc(
            {
                "doctype": "Asset Movement",
                "company": "_Test Company",
                "purpose": "Transfer",
                "transaction_date": frappe.utils.now(),
                "assets": [
                    {
                        "asset": self.owned["asset"],
                        "company": "_Test Company",
                        "source_location": source,
                        "target_location": target,
                        "from_employee": from_employee,
                        "to_employee": self.receiver_employee,
                        "receiver_user": self.receiver,
                        "installation_customer": customer,
                    }
                ],
            }
        ).insert()
        doc = self._approve(doc)
        frappe.set_user(self.receiver)
        acceptance.confirm_receipt(str(doc.name), str(doc.get("assets")[0].name))
        return doc.reload()

    def _close_owned_history(self) -> None:
        frappe.local.db = self._primary_connection
        self._primary_connection.rollback()
        if self._secondary_connection is not None:
            self._secondary_connection.rollback()
        if not self._committed:
            return
        frappe.set_user(self.reviewer)
        for key in ("second", "first"):
            name = self.owned.get(key)
            if name and frappe.db.get_value("Asset Movement", name, "docstatus") == 1:
                apply_workflow(frappe.get_doc("Asset Movement", name), "Cancel Asset Movement")
        frappe.set_user("Administrator")
        frappe.get_doc("Asset", self.owned["asset"]).cancel_movement_entries()
        for key in ("first", "second", "receipt"):
            name = self.owned[key]
            self.assertEqual(frappe.db.get_value("Asset Movement", name, "docstatus"), 2)
            self.assertFalse(
                frappe.db.exists(
                    "Workflow Action",
                    {"reference_doctype": "Asset Movement", "reference_name": name, "status": "Open"},
                )
            )
        self.assertFalse(frappe.db.get_value("Asset", self.owned["asset"], "customer"))
        pending = get_jobs(site=frappe.local.site, key="kwargs").get(frappe.local.site, [])
        self.assertFalse(
            any(
                any(self.owned[key] in str(job) for key in ("asset", "first", "second", "receipt"))
                for job in pending
            )
        )
        # Retain only terminal canceled native history after fixture cleanup.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit

    def test_native_cancellation_conflict_rolls_back_and_stale_snapshot_restores_baseline(self) -> None:
        first = self._install(self.source, self.target, self.owned["customer_1"], None)
        self.owned["first"] = str(first.name)
        second = self._install(self.target, self.source, self.owned["customer_2"], self.receiver_employee)
        self.owned["second"] = str(second.name)
        self.assertEqual(
            frappe.db.get_value("Asset", self.owned["asset"], "customer"), self.owned["customer_2"]
        )
        self.assertEqual(
            frappe.db.get_value("Asset", self.owned["asset"], ["location", "custodian"]),
            (self.source, self.receiver_employee),
        )
        # Publish the exact owned fixture so the second DB connection can see it.
        frappe.db.commit()  # nosemgrep: frappe-manual-commit
        self._committed = True

        with self.primary_connection():
            before_activity = frappe.db.count("Asset Activity", {"asset": self.owned["asset"]})
            before_action = frappe.db.get_all(
                "Workflow Action",
                filters={"reference_doctype": "Asset Movement", "reference_name": second.name},
                fields=["name", "status"],
                order_by="name",
            )
            frappe.db.get_value("Asset Movement", first.name, "name", for_update=True)
            with self.secondary_connection():
                frappe.set_user(self.reviewer)
                with self.assertRaises((frappe.QueryTimeoutError, frappe.QueryDeadlockError)):
                    apply_workflow(frappe.get_doc("Asset Movement", second.name), "Cancel Asset Movement")
                frappe.db.rollback()
            frappe.local.db = self._primary_connection
            self.assertEqual(frappe.db.get_value("Asset Movement", second.name, "docstatus"), 1)
            self.assertEqual(
                frappe.db.get_value("Asset", self.owned["asset"], "customer"), self.owned["customer_2"]
            )
            self.assertEqual(
                frappe.db.get_value("Asset", self.owned["asset"], ["location", "custodian"]),
                (self.source, self.receiver_employee),
            )
            self.assertEqual(
                frappe.db.count("Asset Activity", {"asset": self.owned["asset"]}), before_activity
            )
            self.assertEqual(
                frappe.db.get_all(
                    "Workflow Action",
                    filters={"reference_doctype": "Asset Movement", "reference_name": second.name},
                    fields=["name", "status"],
                    order_by="name",
                ),
                before_action,
            )
            self._primary_connection.rollback()

        with self.primary_connection():
            frappe.db.get_value("Asset Movement", first.name, "workflow_state")
        with self.secondary_connection():
            frappe.set_user(self.reviewer)
            apply_workflow(frappe.get_doc("Asset Movement", first.name), "Cancel Asset Movement")
            # Commit A's native cancellation while the primary RR snapshot stays stale.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
            before_retry_activity = frappe.db.count("Asset Activity", {"asset": self.owned["asset"]})
            before_retry_action = frappe.db.get_all(
                "Workflow Action",
                filters={"reference_doctype": "Asset Movement", "reference_name": second.name},
                fields=["name", "status"],
                order_by="name",
            )
        frappe.local.db = self._primary_connection
        with self.primary_connection():
            frappe.set_user(self.reviewer)
            try:
                apply_workflow(frappe.get_doc("Asset Movement", second.name), "Cancel Asset Movement")
            except (frappe.TimestampMismatchError, frappe.QueryDeadlockError, frappe.QueryTimeoutError):
                frappe.db.rollback()
                self.assertEqual(frappe.db.get_value("Asset Movement", second.name, "docstatus"), 1)
                self.assertEqual(
                    frappe.db.get_value("Asset", self.owned["asset"], "customer"), self.owned["customer_2"]
                )
                self.assertEqual(
                    frappe.db.get_value("Asset", self.owned["asset"], ["location", "custodian"]),
                    (self.source, self.receiver_employee),
                )
                self.assertEqual(
                    frappe.db.count("Asset Activity", {"asset": self.owned["asset"]}),
                    before_retry_activity,
                )
                self.assertEqual(
                    frappe.db.get_all(
                        "Workflow Action",
                        filters={"reference_doctype": "Asset Movement", "reference_name": second.name},
                        fields=["name", "status"],
                        order_by="name",
                    ),
                    before_retry_action,
                )
                apply_workflow(frappe.get_doc("Asset Movement", second.name), "Cancel Asset Movement")
            self.assertFalse(frappe.db.get_value("Asset", self.owned["asset"], "customer"))
            self.assertEqual(
                frappe.db.get_value("Asset", self.owned["asset"], ["location", "custodian"]),
                (self.source, ""),
            )
            # Retain the proven terminal canceled history for the disposable test site.
            frappe.db.commit()  # nosemgrep: frappe-manual-commit
