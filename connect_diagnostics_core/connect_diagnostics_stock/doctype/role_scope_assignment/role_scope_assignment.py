# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import TYPE_CHECKING

import frappe
from frappe import _
from frappe.model.document import Document

from connect_diagnostics_core.api.frappe import role_scope_assignment as assignment_api

if TYPE_CHECKING:
    from frappe.types import DF


class RoleScopeAssignment(Document):
    def validate(self) -> None:
        if not self.is_new():
            lifecycle_operation = self._action
            transitions = {
                ("Pending Owner Approval", "save"): "Request Assignment",
                ("Rejected", "save"): "Reject Assignment",
                ("Active", "submit"): "Approve Assignment",
            }
            transition_key = (str(self.workflow_state or ""), lifecycle_operation)
            if transition_key not in transitions:
                frappe.throw(_("Role Scope Assignments can only be changed through their approved Workflow."))
            transition_action = transitions[transition_key]
            if lifecycle_operation == "save":
                authorized = assignment_api.consume_workflow_transition(
                    self, transition_action, lifecycle_operation
                )
            else:
                authorized = assignment_api.is_authorized_workflow_transition(
                    self, transition_action, lifecycle_operation
                )
            if not authorized:
                frappe.throw(_("Role Scope Assignments can only be changed through their approved Workflow."))
        self._validate_scope()
        if self.is_new():
            self.requested_by = frappe.session.user
            self.requested_at = frappe.utils.now()
            self.workflow_state = None
            self.scope_owner = None
            self.decided_at = None
            self.role_grant_created = 0
            self.role_grant_row = None
            self.user_permission_created = 0
            self.user_permission_row = None

    def before_submit(self) -> None:
        if self.workflow_state != "Active" or not assignment_api.consume_workflow_transition(
            self, "Approve Assignment", "submit"
        ):
            frappe.throw(_("Role Scope Assignment cannot be submitted without its approved Workflow."))

    def before_cancel(self) -> None:
        if self.workflow_state != "Revoked" or not assignment_api.consume_workflow_transition(
            self, "Cancel", "cancel"
        ):
            frappe.throw(_("Role Scope Assignment cannot be cancelled without its approved Workflow."))

    def on_trash(self) -> None:
        frappe.throw(_("Role Scope Assignments cannot be deleted."))

    def _validate_scope(self) -> None:
        if self.scope_type == "Company":
            scope_name = self.company
        elif self.scope_type == "Department":
            scope_name = self.department
        elif self.scope_type == "Warehouse":
            scope_name = self.warehouse
        else:
            frappe.throw(_("Choose Company, Department, or Warehouse scope."))
        if not scope_name:
            frappe.throw(_("Select the exact record for the chosen scope."))
        for fieldname in {"department", "warehouse"} - {self.scope_type.lower()}:
            if self.get(fieldname):
                frappe.throw(_("Only the selected exact scope may be populated."))
        assignment_api.validate_scope_binding(str(self.scope_type), str(scope_name), str(self.company))
        if self.functional_role not in assignment_api.FUNCTIONAL_ROLES:
            frappe.throw(_("The selected functional role is not assignable."))
        if not frappe.db.get_value("User", {"name": self.target_user, "enabled": 1}, "name"):
            frappe.throw(_("Select an enabled target User."))

    if TYPE_CHECKING:
        company: DF.Link
        department: DF.Link | None
        functional_role: DF.Link
        scope_type: DF.Literal["Company", "Department", "Warehouse"]
        target_user: DF.Link
        warehouse: DF.Link | None
        workflow_state: DF.Data | None
