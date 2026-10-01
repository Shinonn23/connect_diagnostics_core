from __future__ import annotations

import json
from typing import Any, cast

import frappe
from frappe.model.workflow import apply_workflow
from frappe.utils import now_datetime

from erpnext.stock.utils import get_stock_balance

from connect_diagnostics_core.api.erpnext import stock_reconciliation_freeze


MAKER = "_test_stock_recon_maker@example.com"
SENDER = "_test_stock_recon_sender@example.com"
APPROVER = "_test_stock_recon_approver@example.com"
COMPANY = "_Test Company with perpetual inventory"
WAREHOUSE = "Finished Goods - TCP1"
ITEM = "_Test Item"
EXPECTED_WORKFLOW = "Connect Stock Reconciliation Blueprint"


def _ensure_demo_user(user: str, roles: set[str], first_name: str) -> None:
    if not frappe.db.exists("User", user):
        doc = frappe.get_doc(
            {
                "doctype": "User",
                "email": user,
                "first_name": first_name,
                "enabled": 1,
                "send_welcome_email": 0,
                "user_type": "System User",
            }
        )
        doc.insert(ignore_permissions=True)
        doc.add_roles(*sorted(roles))

    current_roles = set(frappe.get_roles(user))
    missing_roles = roles - current_roles
    if missing_roles:
        frappe.get_doc("User", user).add_roles(*sorted(missing_roles))

    current_roles = set(frappe.get_roles(user))
    if not frappe.db.get_value("User", user, "enabled"):
        frappe.throw(f"Demo user {user} must be enabled.")
    if "Administrator" in current_roles or "System Manager" in current_roles:
        frappe.throw(f"Demo user {user} must not be privileged.")
    if not roles.issubset(current_roles):
        frappe.throw(f"Demo user {user} is missing roles {sorted(roles - current_roles)}.")
    unexpected_business_roles = current_roles.intersection({"Stock User", "Stock Manager"}) - roles
    if unexpected_business_roles:
        frappe.throw(f"Demo user {user} has conflicting stock roles: {sorted(unexpected_business_roles)}")


def _ensure_demo_thai_tax_settings() -> dict[str, Any]:
    settings = frappe.get_single("Thai Tax Settings")
    matching_rows = [row for row in settings.company_accounts if row.company == COMPANY]
    if len(matching_rows) > 1:
        frappe.throw(f"Thai Tax Settings has duplicate rows for demo company {COMPANY}.")
    if matching_rows:
        return {"company": COMPANY, "created": False, "row_name": matching_rows[0].name}

    row = settings.append("company_accounts", {"company": COMPANY})
    settings.save(ignore_permissions=True)
    return {
        "company": COMPANY,
        "created": True,
        "row_name": row.name,
        "note": "Demo-only company row; production tax-account policy remains unresolved.",
    }


def _remove_demo_thai_tax_settings_row(row_name: str) -> dict[str, Any]:
    row = frappe.db.get_value(
        "Thai Tax Settings Company",
        row_name,
        [
            "parent",
            "parenttype",
            "parentfield",
            "company",
            "sales_tax_account",
            "sales_tax_account_undue",
            "purchase_tax_account",
            "purchase_tax_account_undue",
            "use_doc_name_for_sales_taxinv",
            "create_sales_taxinv_on_zero_tax",
            "manual_keyin_sales_taxinv_on_zero_tax",
        ],
        as_dict=True,
    )
    if not row:
        frappe.throw(f"Demo Thai Tax Settings row {row_name} is missing during cleanup.")
    if (
        row.parent != "Thai Tax Settings"
        or row.parenttype != "Thai Tax Settings"
        or row.parentfield != "company_accounts"
        or row.company != COMPANY
    ):
        frappe.throw(f"Refusing to remove unexpected Thai Tax Settings row {row_name}: {row}")
    business_fields = (
        "sales_tax_account",
        "sales_tax_account_undue",
        "purchase_tax_account",
        "purchase_tax_account_undue",
        "use_doc_name_for_sales_taxinv",
        "create_sales_taxinv_on_zero_tax",
        "manual_keyin_sales_taxinv_on_zero_tax",
    )
    if any(row.get(fieldname) for fieldname in business_fields):
        frappe.throw(f"Refusing to remove modified Thai Tax Settings row {row_name}: {row}")

    settings = frappe.get_single("Thai Tax Settings")
    matching_rows = [child for child in settings.company_accounts if child.name == row_name]
    if len(matching_rows) != 1:
        frappe.throw(f"Expected one demo Thai Tax Settings row {row_name}, found {len(matching_rows)}.")
    settings.remove(matching_rows[0])
    settings.save(ignore_permissions=True)
    if frappe.db.exists("Thai Tax Settings Company", row_name):
        frappe.throw(f"Demo Thai Tax Settings row {row_name} still exists after cleanup.")
    return {"row_name": row_name, "removed": True}


def _preflight() -> dict[str, Any]:
    active = frappe.get_all(
        "Workflow",
        filters={"document_type": "Stock Reconciliation", "is_active": 1},
        pluck="name",
    )
    if active != [EXPECTED_WORKFLOW]:
        frappe.throw(f"Unexpected active Stock Reconciliation Workflow: {active}")

    workflow = frappe.get_doc("Workflow", EXPECTED_WORKFLOW)
    transitions = [
        {
            "action": row.action,
            "state": row.state,
            "next_state": row.next_state,
            "allowed": row.allowed,
            "allow_self_approval": int(row.allow_self_approval),
            "transition_tasks": row.transition_tasks,
        }
        for row in workflow.transitions
    ]
    expected = [
        ("Submit Stock Reconciliation for Review", "Stock User"),
        ("Approve Stock Reconciliation", "Stock Manager"),
        ("Reject Stock Reconciliation", "Stock Manager"),
        ("Post Stock Reconciliation", "Stock Manager"),
        ("Cancel Stock Reconciliation", "Stock Manager"),
    ]
    actual = [(row["action"], row["allowed"]) for row in transitions]
    if actual != expected:
        frappe.throw(f"Unexpected Stock Reconciliation transitions: {actual}")
    if any(row["allow_self_approval"] for row in transitions):
        frappe.throw("The demo Workflow must prohibit self approval.")
    if any(row["transition_tasks"] for row in transitions):
        frappe.throw("The POC expects the baseline Workflow without transition tasks.")

    stock_reconciliation_meta = frappe.get_meta("Stock Reconciliation")
    workflow_field = stock_reconciliation_meta.get_field("workflow_state")
    if not workflow_field or workflow_field.options != "Workflow State":
        frappe.throw("Stock Reconciliation workflow_state field is missing or incompatible.")
    if stock_reconciliation_meta.queue_in_background:
        frappe.throw("The POC requires synchronous Stock Reconciliation submission.")

    required = {
        ("Company", COMPANY),
        ("Warehouse", WAREHOUSE),
        ("Item", ITEM),
        ("Account", "Stock In Hand - TCP1"),
        ("Account", "Stock Adjustment - TCP1"),
        ("Account", "Temporary Opening - TCP1"),
        ("Cost Center", "Main - TCP1"),
    }
    missing = [(doctype, name) for doctype, name in required if not frappe.db.exists(doctype, name)]
    if missing:
        frappe.throw(f"Missing POC master data: {missing}")
    if not frappe.db.get_value("Company", COMPANY, "enable_perpetual_inventory"):
        frappe.throw("POC Company must use perpetual inventory.")
    if frappe.db.exists("Stock Reconciliation", {"owner": MAKER, "company": COMPANY}):
        frappe.throw("A POC reconciliation owned by the demo maker already exists; inspect it first.")

    return {
        "workflow": EXPECTED_WORKFLOW,
        "transitions": transitions,
        "freeze_hook_module": stock_reconciliation_freeze.__file__,
    }


def _balance() -> tuple[float, float]:
    value = get_stock_balance(ITEM, WAREHOUSE, with_valuation_rate=True)
    if isinstance(value, tuple):
        return float(value[0] or 0), float(value[1] or 0)
    return float(value or 0), 0.0


def _difference_account() -> str:
    if frappe.db.sql("select name from `tabStock Ledger Entry` limit 1"):
        return "Stock Adjustment - TCP1"
    return "Temporary Opening - TCP1"


def _new_reconciliation(target_qty: float, valuation_rate: float) -> str:
    timestamp = now_datetime()
    doc = frappe.get_doc(
        {
            "doctype": "Stock Reconciliation",
            "company": COMPANY,
            "purpose": "Stock Reconciliation",
            "posting_date": timestamp.date(),
            "posting_time": timestamp.time(),
            "set_posting_time": 1,
            "expense_account": _difference_account(),
            "cost_center": "Main - TCP1",
            "items": [
                {
                    "item_code": ITEM,
                    "warehouse": WAREHOUSE,
                    "qty": target_qty,
                    "valuation_rate": valuation_rate,
                    "allow_zero_valuation_rate": 0,
                }
            ],
        }
    )
    doc.insert()
    if doc.owner != MAKER or doc.workflow_state != "Stock Reconciliation Draft":
        frappe.throw(f"Unexpected maker or initial Workflow state: {doc.owner}, {doc.workflow_state}")
    return cast(str, doc.name)


def _transition(name: str, action: str, user: str) -> dict[str, Any]:
    frappe.set_user(user)
    doc = frappe.get_doc("Stock Reconciliation", name)
    result = apply_workflow(doc, action)
    return {
        "action": action,
        "actor": user,
        "workflow_state": result.workflow_state,
        "docstatus": int(result.docstatus),
        "modified": str(result.modified),
    }


def _effects(name: str) -> dict[str, Any]:
    sle = frappe.get_all(
        "Stock Ledger Entry",
        filters={"voucher_type": "Stock Reconciliation", "voucher_no": name},
        fields=[
            "name",
            "voucher_detail_no",
            "item_code",
            "warehouse",
            "actual_qty",
            "qty_after_transaction",
            "valuation_rate",
            "stock_value_difference",
            "is_cancelled",
        ],
        order_by="creation, name",
    )
    gl = frappe.get_all(
        "GL Entry",
        filters={"voucher_type": "Stock Reconciliation", "voucher_no": name},
        fields=["name", "account", "debit", "credit", "is_cancelled"],
        order_by="creation, name",
    )
    return {"sle": sle, "gl": gl}


def _history(name: str) -> list[dict[str, Any]]:
    return frappe.get_all(
        "Comment",
        filters={"reference_doctype": "Stock Reconciliation", "reference_name": name},
        fields=["comment_type", "owner", "content", "creation"],
        order_by="creation",
    )


def _recover_positive(name: str, baseline_qty: float) -> dict[str, Any]:
    """Cancel a committed POC posting before propagating a failed assertion."""
    frappe.db.rollback()
    status = frappe.db.get_value(
        "Stock Reconciliation",
        name,
        ["docstatus", "workflow_state"],
        as_dict=True,
    )
    if not status or int(status.docstatus) != 1:
        return {"name": name, "required": False, "status": status}

    step = _transition(name, "Cancel Stock Reconciliation", APPROVER)
    frappe.db.commit()
    cancelled = frappe.get_doc("Stock Reconciliation", name)
    restored_qty, restored_rate = _balance()
    if cancelled.docstatus != 2 or cancelled.workflow_state != "Stock Reconciliation Cancelled":
        frappe.throw("Recovery did not reach the native cancelled state.")
    if restored_qty != baseline_qty:
        frappe.throw(f"Recovery did not restore baseline quantity: {restored_qty}")
    return {
        "name": name,
        "required": True,
        "step": step,
        "balance": {"qty": restored_qty, "valuation_rate": restored_rate},
        "effects": _effects(name),
    }


def execute() -> None:
    original_user = frappe.session.user
    evidence: dict[str, Any] = {}
    positive_name: str | None = None
    baseline_qty: float | None = None
    demo_thai_tax_row: str | None = None
    try:
        frappe.set_user("Administrator")
        evidence["preflight"] = _preflight()
        _ensure_demo_user(MAKER, {"Stock User", "Stock Manager"}, "_Test Stock Recon Maker")
        _ensure_demo_user(SENDER, {"Stock User", "Stock Manager"}, "_Test Stock Recon Sender")
        _ensure_demo_user(APPROVER, {"Stock Manager"}, "_Test Stock Recon Approver")
        evidence["demo_thai_tax_settings"] = _ensure_demo_thai_tax_settings()
        if evidence["demo_thai_tax_settings"]["created"]:
            demo_thai_tax_row = cast(str, evidence["demo_thai_tax_settings"]["row_name"])
        frappe.db.commit()

        evidence["users"] = {
            MAKER: sorted(frappe.get_roles(MAKER)),
            SENDER: sorted(frappe.get_roles(SENDER)),
            APPROVER: sorted(frappe.get_roles(APPROVER)),
        }
        evidence["limitations"] = [
            "The dual-role sender could approve/post under the current configuration; "
            "this POC does not prove sender-versus-approver SoD.",
            "The POC proves backend Workflow and native SLE/GL mechanics only, not production permissions or policy.",
        ]
        baseline_qty, baseline_rate = _balance()
        valuation_rate = baseline_rate or 100.0
        evidence["baseline"] = {"qty": baseline_qty, "valuation_rate": baseline_rate}

        frappe.set_user(MAKER)
        rejected_name = _new_reconciliation(baseline_qty + 1, valuation_rate)
        frappe.db.commit()
        reject_steps = [
            _transition(rejected_name, "Submit Stock Reconciliation for Review", SENDER),
            _transition(rejected_name, "Reject Stock Reconciliation", APPROVER),
        ]
        frappe.db.commit()
        rejected = frappe.get_doc("Stock Reconciliation", rejected_name)
        rejected_effects = _effects(rejected_name)
        if rejected.docstatus != 0 or rejected.workflow_state != "Stock Reconciliation Rejected":
            frappe.throw("Rejected POC document has an unexpected terminal state.")
        if rejected_effects["sle"] or rejected_effects["gl"]:
            frappe.throw("Rejected POC document created ledger effects.")
        evidence["rejected"] = {
            "name": rejected_name,
            "owner": rejected.owner,
            "difference_account": rejected.expense_account,
            "steps": reject_steps,
            "effects": rejected_effects,
            "history": _history(rejected_name),
        }

        frappe.set_user(MAKER)
        positive_name = _new_reconciliation(baseline_qty + 3, valuation_rate)
        frappe.db.commit()
        positive_steps = [_transition(positive_name, "Submit Stock Reconciliation for Review", SENDER)]
        frappe.db.commit()

        maker_denial: dict[str, Any]
        try:
            _transition(positive_name, "Approve Stock Reconciliation", MAKER)
        except frappe.ValidationError as exc:
            frappe.db.rollback()
            if type(exc) is not frappe.ValidationError or str(exc) != "Self approval is not allowed":
                raise
            denied_doc = frappe.get_doc("Stock Reconciliation", positive_name)
            if (
                denied_doc.docstatus != 0
                or denied_doc.workflow_state != "Stock Reconciliation Pending Review"
            ):
                frappe.throw("Denied maker action changed the Stock Reconciliation state.")
            maker_denial = {
                "type": type(exc).__name__,
                "message": str(exc),
                "workflow_state": denied_doc.workflow_state,
                "docstatus": int(denied_doc.docstatus),
            }
        else:
            frappe.throw("Maker unexpectedly approved the Stock Reconciliation.")

        positive_steps.append(_transition(positive_name, "Approve Stock Reconciliation", APPROVER))
        frappe.db.commit()
        positive_steps.append(_transition(positive_name, "Post Stock Reconciliation", APPROVER))
        frappe.db.commit()

        submitted = frappe.get_doc("Stock Reconciliation", positive_name)
        submitted_effects = _effects(positive_name)
        submitted_qty, submitted_rate = _balance()
        if submitted.docstatus != 1 or submitted.workflow_state != "Stock Reconciliation Submitted":
            frappe.throw("Positive POC document did not reach submitted state.")
        if submitted_qty != baseline_qty + 3:
            frappe.throw(f"Unexpected submitted stock balance: {submitted_qty}")
        active_sle = [row for row in submitted_effects["sle"] if not row.is_cancelled]
        active_gl = [row for row in submitted_effects["gl"] if not row.is_cancelled]
        if len(active_sle) != 1:
            frappe.throw(f"Expected one active SLE, found {len(active_sle)}")
        if len(active_gl) != 2:
            frappe.throw(f"Expected two active GL entries, found {len(active_gl)}")
        if round(sum(float(row.debit or 0) for row in active_gl), 2) != round(
            sum(float(row.credit or 0) for row in active_gl), 2
        ):
            frappe.throw("POC GL entries are not balanced.")
        evidence["submitted"] = {
            "name": positive_name,
            "owner": submitted.owner,
            "difference_account": submitted.expense_account,
            "maker_denial": maker_denial,
            "steps": positive_steps,
            "balance": {"qty": submitted_qty, "valuation_rate": submitted_rate},
            "effects": submitted_effects,
            "history": _history(positive_name),
        }

        cancel_step = _transition(positive_name, "Cancel Stock Reconciliation", APPROVER)
        frappe.db.commit()
        cancelled = frappe.get_doc("Stock Reconciliation", positive_name)
        cancelled_effects = _effects(positive_name)
        restored_qty, restored_rate = _balance()
        if cancelled.docstatus != 2 or cancelled.workflow_state != "Stock Reconciliation Cancelled":
            frappe.throw("POC document did not reach the native cancelled state.")
        if restored_qty != baseline_qty:
            frappe.throw(f"Cancellation did not restore baseline quantity: {restored_qty}")
        if round(
            sum(float(row.debit or 0) - float(row.credit or 0) for row in cancelled_effects["gl"]), 2
        ) != 0:
            frappe.throw("Cancelled POC GL entries do not net to zero.")
        evidence["cancelled"] = {
            "step": cancel_step,
            "balance": {"qty": restored_qty, "valuation_rate": restored_rate},
            "effects": cancelled_effects,
            "history": _history(positive_name),
        }

        if demo_thai_tax_row:
            evidence["demo_thai_tax_settings"]["cleanup"] = _remove_demo_thai_tax_settings_row(
                demo_thai_tax_row
            )
            frappe.db.commit()

        print("POC_RESULT=" + json.dumps(evidence, default=str, sort_keys=True))
    except Exception as original_error:
        frappe.db.rollback()
        try:
            recovery: dict[str, Any] = {}
            if positive_name and baseline_qty is not None:
                recovery = _recover_positive(positive_name, baseline_qty)
            if demo_thai_tax_row:
                recovery["demo_thai_tax_settings"] = _remove_demo_thai_tax_settings_row(
                    demo_thai_tax_row
                )
                frappe.db.commit()
            print("POC_RECOVERY=" + json.dumps(recovery, default=str, sort_keys=True))
        except Exception as recovery_error:
            frappe.db.rollback()
            print(
                "RECOVERY_FAILED="
                + json.dumps(
                    {
                        "name": positive_name,
                        "original_error": str(original_error),
                        "recovery_error": str(recovery_error),
                    },
                    sort_keys=True,
                )
            )
            raise recovery_error from original_error
        raise
    finally:
        frappe.set_user(original_user)


execute()
