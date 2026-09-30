# Sales Order workflow inventory — local.test — 2026-09-23

## Scope and method

Read-only inspection through the approved Frappe Bench console on site `local.test`. No document,
configuration, schema, or transaction was written. The inspection queried native Frappe APIs for
Sales Order Workflows, Workflow Actions, code-managed Custom Fields, Sales Order counts/states, and
Workflow Action Master presence.

- Inspection time: `2026-09-23 19:28:58 +07 (+0700)` from the Bench host.
- Command: `bench --site local.test console`
- Site System Settings timezone returned by `frappe.utils.get_system_timezone()`:
  `Asia/Kolkata` (this differs from the repository-required `Asia/Bangkok` target timezone and must
  be corrected or explicitly dispositioned before timestamp-sensitive migration/acceptance work).
- Canonical inventory SHA-256:
  `0bb5b54d42ecebd90d4412698c4fc14d873ea1d805961a690934a1af7fcec8dc`

The fingerprint was calculated from the compact, sorted JSON representation of the `config`
mapping built by this bounded console query:

```python
import hashlib
import json

w = frappe.get_doc("Workflow", "Connect Sales Order Blueprint")
config = {
    "target": "local.test",
    "system_timezone": frappe.utils.get_system_timezone(),
    "workflows": frappe.get_all(
        "Workflow",
        filters={"document_type": "Sales Order"},
        fields=["name", "is_active", "workflow_state_field", "modified"],
        order_by="name",
    ),
    "states": [
        {
            "state": row.get("state"),
            "doc_status": row.get("doc_status"),
            "allow_edit": row.get("allow_edit"),
        }
        for row in w.states
    ],
    "transitions": [
        {
            "state": row.get("state"),
            "action": row.get("action"),
            "next_state": row.get("next_state"),
            "allowed": row.get("allowed"),
            "allow_self_approval": row.get("allow_self_approval"),
            "condition": row.get("condition"),
            "workflow_builder_id": row.get("workflow_builder_id"),
            "workflow_transition_tasks": row.get("workflow_transition_tasks"),
        }
        for row in w.transitions
    ],
    "workflow_action_master_presence": {
        name: bool(frappe.db.exists("Workflow Action Master", name))
        for name in [
            "Submit Sales Order for Review",
            "Approve Sales Order",
            "Reject Sales Order",
            "Post Sales Order",
            "Cancel Sales Order",
        ]
    },
    "workflow_action_status_counts": {
        status: frappe.db.count(
            "Workflow Action",
            {"reference_doctype": "Sales Order", "status": status},
        )
        for status in ["Open", "Completed", "Cancelled"]
    },
    "sales_order_docstatus_counts": {
        str(docstatus): frappe.db.count("Sales Order", {"docstatus": docstatus})
        for docstatus in [0, 1, 2]
    },
    "workflow_state_fields": frappe.get_all(
        "Custom Field",
        filters={
            "dt": "Sales Order",
            "fieldname": [
                "in",
                [
                    "workflow_state",
                    "approval_critical_digest",
                    "approval_reviewer_user",
                    "approval_authorized_user",
                ],
            ],
        },
        fields=[
            "fieldname",
            "fieldtype",
            "options",
            "read_only",
            "hidden",
            "no_copy",
            "allow_on_submit",
        ],
        order_by="fieldname",
    ),
}
canonical = json.dumps(
    config,
    default=str,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
print(hashlib.sha256(canonical.encode()).hexdigest())
print(json.dumps(config, default=str, ensure_ascii=False, indent=2))
```

## Observed configuration on local.test

- Exactly one Workflow targets `Sales Order`: `Connect Sales Order Blueprint`.
- It is active, uses `workflow_state`, and reports modified time
  `2026-09-17 00:00:00`.
- States and roles match the repository fixture:
  - Draft (`docstatus 0`, Sales User)
  - Pending Review (`docstatus 0`, Sales User)
  - Approved (`docstatus 0`, Sales Manager)
  - Rejected (`docstatus 0`, Sales User)
  - Submitted (`docstatus 1`, Sales Manager)
  - Cancelled (`docstatus 2`, Sales Manager)
- The five configured transitions have no conditions and no transition tasks. Each has
  `allow_self_approval = 0`:
  - Submit Sales Order for Review
  - Approve Sales Order
  - Reject Sales Order
  - Post Sales Order
  - Cancel Sales Order
- All five matching Workflow Action Master records exist.

## Existing documents and pending work on local.test

- Sales Orders: `0` total (`0` draft, `0` submitted, `0` cancelled).
- Sales Order Workflow Actions: `0` Open, `0` Completed, `0` Cancelled.
- There is therefore no Sales Order document or Workflow Action on `local.test` requiring
  migration disposition at this checkpoint. This statement does not clear another target.

## Existing fields on local.test

Of the inspected workflow/approval fields, only `workflow_state` exists on Sales Order. It is a
hidden `Link` to Workflow State with `no_copy = 1` and `allow_on_submit = 1`.

The following fields do not exist on Sales Order at this checkpoint:

- `approval_critical_digest`
- `approval_reviewer_user`
- `approval_authorized_user`

## Native ERPNext v16 credit/commercial contract

The locally installed ERPNext source was inspected at commit
`12cd563fb9a79731f75ae2a45b1446a0a2dd9e74` (Frappe commit
`c1f1e8ec3708750d7254f7f99d869ffb9886f19f`). The local Markdown documentation
path configured by the repository skill, `/home/frappe/ERPNext Docs Markdown/`, was not present, so
installed source was used as the authoritative fallback.

- `erpnext/selling/doctype/sales_order/sales_order.py` calls native credit-limit validation and
  `Authorization Control.validate_approving_authority()` from `SalesOrder.on_submit()`. The
  approving-authority check receives `base_grand_total`, so its amount basis is company currency.
- `erpnext/selling/doctype/customer/customer.py` resolves credit limits in this order: Customer and
  Company, Customer Group and Company when not bypassed, then Company default. Its exposure
  calculation includes Customer GL outstanding, the unbilled balance of submitted/open Sales
  Orders, and submitted standalone Delivery Notes not already linked to a Sales Order/Invoice.
- The native credit-controller role in Accounts Settings may bypass a crossed credit limit. A
  Customer Credit Limit row may instead set `bypass_credit_limit_check`, which skips the Sales
  Order check and changes downstream Delivery Note/Sales Invoice recheck behavior.
- Native Authorization Rules can constrain Sales Order by Grand Total, Average Discount,
  Customerwise Discount, Itemwise Discount, or Item Group wise Discount and can name an approving
  role/user above the configured value.
- ERPNext item validation separately enforces each Item's `max_discount` when configured.

These mechanisms are preserved inputs to D-SALES; their existence does not choose which one routes
Commercial review, Credit review, or final approval.

## Native policy configuration on local.test

A second read-only Bench query found no configured test policy:

- Accounts Settings credit-controller role: empty.
- Overdue-billing threshold enforcement: disabled; bypass role empty.
- Sales Order Authorization Rules: `0`.
- Customer Credit Limit rows: `0` (including `0` bypass rows).
- Companies with a positive default credit limit: `0`.

Consequently `local.test` currently provides no approved or even provisional amount/discount/credit
route values for the requested test matrix. Tests cannot derive D-SALES thresholds or authority
from current site configuration.

## Interpretation and limits

The clean `local.test` inventory removes a local pending-document collision for migration rehearsal,
but it does not approve the desired route, policy values, shared identity contract, or mutation of
another environment. TSK-602 still must provide the authoritative collision/pending-action
disposition for every deployment target, and the migration must recheck the fingerprint at runtime.

The active fixture is not sufficient submit protection: it has no policy conditions, transition
tasks, approval digest fields, or Sales Order-specific server guard. Runtime implementation remains
blocked by the decisions and shared contracts listed in the TSK-525 slice plan.
