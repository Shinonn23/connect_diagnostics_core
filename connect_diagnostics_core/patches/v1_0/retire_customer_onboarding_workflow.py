# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Let Sales open a Customer and sell to it in the same breath.

Onboarding used to take three people: Sales raised the Customer, an IT-UB
employee verified it was not a duplicate, and an accounting reviewer activated
it. Until that finished the Customer stayed ``disabled``, so nothing could be
ordered. For a cash walk-in that queue cost more than the sale.

This patch removes the queue. Every Customer that was mid-flight is enabled, the
``Customer Onboarding`` workflow and its states are deleted, and the fields that
existed only to feed it are dropped:

* the four readiness Selects and their summary were recalculated and rewritten on
  every Customer, Address and Contact save, purely to be read back by the
  activation gate — they are now calculated on demand instead of stored
* ``customer_onboarding_state`` and ``correction_reason`` belonged to the workflow
* ``no_delivery_required`` / ``no_delivery_reason`` existed only to waive the
  delivery half of that gate

Credit is unaffected: it still runs through ``Customer Credit Request`` and its
own approval, which now covers GOV. HOSPITAL too.

Idempotent — every step is skipped when it has already been done.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import delete_custom_fields

WORKFLOW_NAME = "Customer Onboarding"
ONBOARDING_STATE_FIELD = "customer_onboarding_state"
ACTIVE_STATE = "Customer Active"

RETIRED_FIELDS = (
    "customer_onboarding_section",
    ONBOARDING_STATE_FIELD,
    "correction_reason",
    "readiness_section",
    "quotation_readiness",
    "delivery_readiness",
    "tax_invoice_readiness",
    "email_readiness",
    "customer_readiness_summary",
    "no_delivery_required",
    "no_delivery_reason",
)

RETIRED_WORKFLOW_STATES = (
    "Customer Request",
    "Customer Pending Duplicate Verification",
    "Customer Pending Accounting & Credit Review",
    ACTIVE_STATE,
)

RETIRED_ACTIONS = ("Send for duplicate verification", "Duplicate verified", "Activate customer")

RETIRED_ROLE = "Customer Duplicate Verifier"
RETIRED_ROLE_PROFILE = "Customer Duplicate Verifier Add-on"


def execute() -> None:
    """Enable every stranded Customer, then remove the workflow and its fields."""
    _enable_customers_stuck_in_onboarding()
    _delete_workflow()
    _delete_retired_role()
    delete_custom_fields({"Customer": list(RETIRED_FIELDS)}, bypass_hooks=True)
    frappe.clear_cache(doctype="Customer")
    frappe.db.commit()


def _enable_customers_stuck_in_onboarding() -> None:
    """Release Customers the queue had disabled.

    Only those the workflow itself disabled are touched. A Customer disabled
    deliberately, which never reached the active state, keeps that decision.
    """
    if not frappe.db.has_column("Customer", ONBOARDING_STATE_FIELD):
        return

    stranded = frappe.get_all(
        "Customer",
        filters={"disabled": 1, ONBOARDING_STATE_FIELD: ["in", RETIRED_WORKFLOW_STATES[:-1]]},
        pluck="name",
    )
    for name in stranded:
        frappe.db.set_value("Customer", name, "disabled", 0, update_modified=False)


def _delete_workflow() -> None:
    if frappe.db.exists("Workflow", WORKFLOW_NAME):
        frappe.delete_doc("Workflow", WORKFLOW_NAME, force=True, ignore_permissions=True)

    for state in RETIRED_WORKFLOW_STATES:
        if frappe.db.exists("Workflow State", state):
            frappe.delete_doc("Workflow State", state, force=True, ignore_permissions=True)

    for action in RETIRED_ACTIONS:
        if frappe.db.exists("Workflow Action Master", action):
            frappe.delete_doc("Workflow Action Master", action, force=True, ignore_permissions=True)


def _delete_retired_role() -> None:
    """Remove the duplicate verifier role and every reference to it.

    The child rows must go **before** the masters. A ``User Role Profile`` row
    pointing at a deleted Role Profile fails link validation the next time that
    User is saved, which breaks the whole migration rather than just this patch.
    """
    frappe.db.delete("User Role Profile", {"role_profile": RETIRED_ROLE_PROFILE})
    frappe.db.delete("Has Role", {"role": RETIRED_ROLE})
    frappe.db.delete("Custom DocPerm", {"role": RETIRED_ROLE})
    frappe.db.set_value(
        "User",
        {"role_profile_name": RETIRED_ROLE_PROFILE},
        "role_profile_name",
        None,
        update_modified=False,
    )

    if frappe.db.exists("Role Profile", RETIRED_ROLE_PROFILE):
        frappe.delete_doc("Role Profile", RETIRED_ROLE_PROFILE, force=True, ignore_permissions=True)
    if frappe.db.exists("Role", RETIRED_ROLE):
        frappe.delete_doc("Role", RETIRED_ROLE, force=True, ignore_permissions=True)
