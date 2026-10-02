# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Server-side approval boundary for the native Purchase Order Workflow."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import frappe
from frappe import _
from frappe.core.doctype.file.file import File
from frappe.model.document import Document
from frappe.utils import get_files_path, now_datetime
from frappe.workflow.doctype.workflow_action.workflow_action import (
    update_completed_workflow_actions_using_role,
)

from connect_diagnostics_core.api.frappe.approval_controls import (
    authorize_workflow_field_write,
    consume_approval_field_grant,
    critical_digest,
    require_distinct_actors,
    require_permission,
    resolve_user,
)

DIGEST_VERSION = "purchase-order-commitment-v1"
REVIEW_STATE = "Purchase Order Pending Review"
APPROVAL_STATE = "Purchase Order Pending Approval"
APPROVED_STATE = "Purchase Order Approved"
SUBMITTED_STATE = "Purchase Order Submitted"
CANCELLED_STATE = "Purchase Order Cancelled"
_EXECUTION_FLAG = "purchase_order_workflow_execution"
_RETURN_ROUTE = "purchase-order-return"
_RETURN_ACTION = "Return Purchase Order"
_RETURN_COMPLETION = "complete-return-action"
_RETURN_PROOF = "_purchase_order_return_action_proof"
_RETURN_ROLES = {
    REVIEW_STATE: ("Purchase Manager", {"Purchase Manager"}),
    APPROVAL_STATE: ("C-Level Approver", {"C-Level Approver"}),
    APPROVED_STATE: ("C-Level Approver", {"Purchase Manager"}),
}

# This is deliberately explicit.  Changes to this map are a digest-schema revision.
COMMITMENT_FIELDS: Mapping[str, tuple[str, ...]] = {
    "Purchase Order": (
        "owner",
        "supplier",
        "company",
        "transaction_date",
        "transaction_time",
        "schedule_date",
        "order_confirmation_no",
        "order_confirmation_date",
        "currency",
        "conversion_rate",
        "buying_price_list",
        "price_list_currency",
        "plc_conversion_rate",
        "party_account_currency",
        "ignore_pricing_rule",
        "supplier_address",
        "contact_person",
        "shipping_address",
        "billing_address",
        "dispatch_address",
        "drop_ship",
        "customer",
        "customer_contact_person",
        "set_warehouse",
        "set_from_warehouse",
        "set_reserve_warehouse",
        "supplier_warehouse",
        "shipping_rule",
        "incoterm",
        "named_place",
        "is_subcontracted",
        "is_old_subcontracting_flow",
        "is_internal_supplier",
        "represents_company",
        "inter_company_order_reference",
        "ref_sq",
        "taxes_and_charges",
        "tax_category",
        "apply_discount_on",
        "base_discount_amount",
        "additional_discount_percentage",
        "discount_amount",
        "disable_rounded_total",
        "payment_terms_template",
        "tc_name",
        "terms",
        "cost_center",
        "project",
        "department",
        "territory",
        "p2p_exception_reason",
        "custom_delivery_by",
        "eta",
        "custom_eta",
        "total_qty",
        "base_total",
        "total",
        "base_net_total",
        "net_total",
        "base_taxes_and_charges_added",
        "base_taxes_and_charges_deducted",
        "base_total_taxes_and_charges",
        "taxes_and_charges_added",
        "taxes_and_charges_deducted",
        "total_taxes_and_charges",
        "base_grand_total",
        "grand_total",
        "base_rounding_adjustment",
        "rounding_adjustment",
        "base_rounded_total",
        "rounded_total",
    ),
    "items": (
        "item_code",
        "supplier_part_no",
        "item_name",
        "description",
        "item_group",
        "brand",
        "manufacturer",
        "manufacturer_part_no",
        "qty",
        "uom",
        "stock_uom",
        "conversion_factor",
        "stock_qty",
        "price_list_rate",
        "base_price_list_rate",
        "discount_percentage",
        "discount_amount",
        "margin_type",
        "margin_rate_or_amount",
        "rate_with_margin",
        "base_rate_with_margin",
        "rate",
        "amount",
        "base_rate",
        "base_amount",
        "net_rate",
        "net_amount",
        "base_net_rate",
        "base_net_amount",
        "distributed_discount_amount",
        "item_tax_rate",
        "item_tax_template",
        "schedule_date",
        "expected_delivery_date",
        "warehouse",
        "from_warehouse",
        "material_request",
        "material_request_item",
        "supplier_quotation",
        "supplier_quotation_item",
        "blanket_order",
        "blanket_order_rate",
        "against_blanket_order",
        "sales_order",
        "sales_order_item",
        "project",
        "cost_center",
        "department",
        "territory",
        "expense_account",
        "is_free_item",
        "delivered_by_supplier",
        "bom",
        "include_exploded_items",
        "is_fixed_asset",
        "fg_item",
        "fg_item_qty",
        "production_plan",
        "production_plan_item",
        "production_plan_sub_assembly_item",
        "product_bundle",
        "sales_order_packed_item",
        "wip_composite_asset",
        "job_card",
    ),
    "taxes": (
        "category",
        "add_deduct_tax",
        "charge_type",
        "row_id",
        "allocate_full_amount_to_stock_items",
        "included_in_print_rate",
        "account_head",
        "cost_center",
        "project",
        "department",
        "territory",
        "description",
        "rate",
        "tax_amount",
        "tax_amount_after_discount_amount",
        "base_tax_amount",
        "base_tax_amount_after_discount_amount",
        "total",
        "base_total",
        "included_in_paid_amount",
        "account_currency",
        "is_tax_withholding_account",
        "net_amount",
        "base_net_amount",
        "set_by_item_tax_template",
        "dont_recompute_tax",
    ),
    "payment_schedule": (
        "payment_term",
        "description",
        "due_date",
        "invoice_portion",
        "payment_amount",
        "base_payment_amount",
        "mode_of_payment",
        "discount_date",
        "discount_type",
        "discount",
        "due_date_based_on",
        "credit_days",
        "credit_months",
        "discount_validity_based_on",
        "discount_validity",
    ),
    "supplied_items": (
        "main_item_code",
        "rm_item_code",
        "required_qty",
        "rate",
        "amount",
        "bom_detail_no",
        "reference_name",
        "conversion_factor",
        "stock_uom",
        "reserve_warehouse",
    ),
}
SNAPSHOT_FIELDS = frozenset(
    {
        "approval_critical_digest",
        "approval_digest_version",
        "approval_reviewer_user",
        "approval_authorized_user",
        "checked_by",
        "checked_at",
        "checked_signature",
        "authorized_by",
        "authorized_at",
        "authorized_signature",
    }
)


def _row_payload(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {"name": row.get("name"), **{field: row.get(field) for field in fields}}


def _selection_evidence_digest(doc: Document | Mapping[str, Any], url: str) -> str:
    name = str(doc.get("name") or "")
    if not name or not url.startswith("/private/files/"):
        frappe.throw(
            _("Supplier selection evidence must be a private local File attached to this Purchase Order.")
        )
    try:
        candidates = frappe.db.get_values(
            "File",
            filters={
                "file_url": url,
                "attached_to_doctype": "Purchase Order",
                "attached_to_name": name,
                "attached_to_field": "supplier_selection_evidence",
            },
            fieldname="name",
            pluck=True,
            for_update=True,
            wait=False,
            order_by="name",
        )
        if len(candidates) != 1:
            frappe.throw(_("Supplier selection evidence must identify one attached File."))
        file = cast(File, frappe.get_doc("File", candidates[0], for_update=True))
        if (
            file.get("file_url") != url
            or file.get("attached_to_doctype") != "Purchase Order"
            or file.get("attached_to_name") != name
            or file.get("attached_to_field") != "supplier_selection_evidence"
            or not file.get("is_private")
            or file.get("is_remote_file")
            or file.get("is_folder")
        ):
            frappe.throw(_("Supplier selection evidence File changed or is not private and local."))
        file.validate_file_url()
        file.validate_file_path()
        path = Path(file.get_full_path()).resolve(strict=True)
        if not path.is_relative_to(Path(get_files_path(is_private=1)).resolve()):
            frappe.throw(_("Supplier selection evidence is outside the private files directory."))
        with path.open("rb") as handle:
            return sha256(handle.read()).hexdigest()
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw(_("Supplier selection evidence is being updated. Please retry."))
    except (OSError, ValueError):
        frappe.throw(_("Supplier selection evidence cannot be read. Please attach a local File."))
    raise AssertionError("Supplier selection evidence validation did not return")


def build_commitment_payload(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Build the immutable server-side input to the approved digest schema."""
    payload = _commitment_projection(doc)
    if "supplier_selection_evidence" in payload:
        evidence = str(payload["supplier_selection_evidence"])
        payload["supplier_selection_evidence_sha256"] = (
            _selection_evidence_digest(doc, evidence) if evidence else None
        )
    return payload


def _commitment_projection(doc: Document | Mapping[str, Any]) -> dict[str, Any]:
    """Project critical values without reading mutable File bytes for an authorized Return."""
    get = doc.get
    payload: dict[str, Any] = {field: get(field) for field in COMMITMENT_FIELDS["Purchase Order"]}
    reason = str(get("supplier_selection_reason") or "").strip()
    evidence = str(get("supplier_selection_evidence") or "")
    if reason or evidence:
        payload["supplier_selection_reason"] = reason
        payload["supplier_selection_evidence"] = evidence
    for table in ("items", "taxes", "payment_schedule", "supplied_items"):
        payload[table] = [_row_payload(row, COMMITMENT_FIELDS[table]) for row in (get(table) or [])]
    return payload


def _validate_supplier_selection(doc: Document) -> None:
    """Distinguish exact submitted quotation lineage from a documented Direct PO."""
    rows = doc.get("items") or []
    quoted: set[str] = set()
    direct = False
    for row in rows:
        quote = str(row.get("supplier_quotation") or "")
        detail = str(row.get("supplier_quotation_item") or "")
        if bool(quote) != bool(detail):
            frappe.throw(_("Supplier Quotation references must include both header and item."))
        if quote:
            quoted.add(quote)
        else:
            direct = True
    try:
        source_rows: dict[str, dict[str, Any]] = {}
        for name in sorted(quoted):
            header = frappe.db.get_value(
                "Supplier Quotation",
                name,
                ["name", "docstatus", "supplier", "company", "currency"],
                as_dict=True,
                for_update=True,
                wait=False,
            )
            if (
                not header
                or header.docstatus != 1
                or any(header.get(field) != doc.get(field) for field in ("supplier", "company", "currency"))
            ):
                frappe.throw(
                    _("Supplier Quotation must be submitted for the same supplier, company, and currency.")
                )
            children = frappe.db.get_values(
                "Supplier Quotation Item",
                filters={"parent": name, "parenttype": "Supplier Quotation", "parentfield": "items"},
                fieldname=["name", "parent", "item_code"],
                as_dict=True,
                for_update=True,
                wait=False,
                order_by="name",
            )
            source = cast(Document, frappe.get_doc("Supplier Quotation", name))
            locked_rows = {str(row.name): (row.get("parent"), row.get("item_code")) for row in children}
            loaded_rows = {
                str(row.name): (row.get("parent"), row.get("item_code")) for row in source.get("items", [])
            }
            if locked_rows != loaded_rows:
                frappe.throw(_("Supplier Quotation items changed while being checked. Please retry."))
            source_rows[name] = {str(row.name): row for row in children}
        for row in rows:
            quote = str(row.get("supplier_quotation") or "")
            if quote:
                child = source_rows[quote].get(str(row.get("supplier_quotation_item")))
                if (
                    not child
                    or child.get("parent") != quote
                    or child.get("item_code") != row.get("item_code")
                ):
                    frappe.throw(_("Supplier Quotation item must belong to the selected quotation and Item."))
    except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
        frappe.throw(_("Supplier Quotation is being updated. Please retry."))
    if direct and (
        not str(doc.get("supplier_selection_reason") or "").strip()
        or not doc.get("supplier_selection_evidence")
    ):
        frappe.throw(_("Direct Purchase Orders require a supplier selection reason and attached evidence."))


def _normalize_native_numbers(value: Any) -> Any:
    """Treat ERPNext's integer-to-float normalization as the same amount."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {key: _normalize_native_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_native_numbers(item) for item in value]
    return value


_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_DATETIME_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?\Z")
_TIME_PATTERN = re.compile(r"([0-9]{1,3}):([0-9]{1,2}):([0-9]{1,2})(?:\.([0-9]{1,6}))?\Z")


def _native_temporal(value: Any, fieldtype: str | None) -> Any:
    """Restore only valid JSON temporal strings to their native DB value types."""
    if not isinstance(value, str):
        return value
    try:
        if fieldtype == "Date" and _DATE_PATTERN.fullmatch(value) and value != "0001-01-01":
            return date.fromisoformat(value)
        if (
            fieldtype == "Datetime"
            and _DATETIME_PATTERN.fullmatch(value)
            and not value.startswith("0001-01-01")
        ):
            return datetime.fromisoformat(value)
        if fieldtype == "Time":
            match = _TIME_PATTERN.fullmatch(value)
            if match:
                hours, minutes, seconds, fraction = match.groups()
                if int(hours) <= 838 and int(minutes) < 60 and int(seconds) < 60:
                    return timedelta(
                        hours=int(hours),
                        minutes=int(minutes),
                        seconds=int(seconds),
                        microseconds=int((fraction or "0").ljust(6, "0")),
                    )
    except ValueError:
        pass
    return value


def _normalize_native_temporals(payload: dict[str, Any]) -> dict[str, Any]:
    meta = frappe.get_meta("Purchase Order")
    for field in COMMITMENT_FIELDS["Purchase Order"]:
        df = meta.get_field(field)
        if df and df.fieldtype in ("Date", "Datetime", "Time"):
            payload[field] = _native_temporal(payload[field], df.fieldtype)
    for table in ("items", "taxes", "payment_schedule", "supplied_items"):
        table_df = meta.get_field(table)
        if not table_df or not table_df.options:
            continue
        row_meta = frappe.get_meta(table_df.options)
        for field in COMMITMENT_FIELDS[table]:
            df = row_meta.get_field(field)
            if df and df.fieldtype in ("Date", "Datetime", "Time"):
                for row in payload[table]:
                    row[field] = _native_temporal(row[field], df.fieldtype)
    return payload


def get_commitment_digest(doc: Document | Mapping[str, Any]) -> str:
    """Return the versioned digest of all commitment-critical values."""
    return critical_digest(
        _normalize_native_numbers(_normalize_native_temporals(build_commitment_payload(doc)))
    )


def _employee_snapshot() -> tuple[str, str]:
    employee = cast(
        Mapping[str, Any],
        frappe.db.get_value(
            "Employee",
            {"user_id": frappe.session.user},
            ["name", "approval_signature"],
            as_dict=True,
        ),
    )
    if not employee:
        frappe.throw(_("An Employee record is required for Purchase Order approval."))
    signature = str(employee.get("approval_signature") or "")
    if not signature:
        frappe.throw(_("An approval signature is required for Purchase Order approval."))
    return str(employee.get("name") or ""), signature


def capture_maker_snapshot(doc: Document, method: str | None = None) -> None:
    """Record the active owner as the unsigned maker of the native review route."""
    del method
    require_permission(doc, "write")
    owner = resolve_user(str(doc.get("owner") or ""))
    actor = resolve_user(str(frappe.session.user or ""))
    if owner != actor:
        frappe.throw(_("Only the Purchase Order owner can send it for review."))
    doc.set("approval_maker_user", actor)


def capture_review_snapshot(doc: Document) -> None:
    """Workflow task: sign the current PO revision as reviewed."""
    require_permission(doc, "write")
    _validate_supplier_selection(doc)
    employee, signature = _employee_snapshot()
    require_distinct_actors(str(doc.get("owner") or ""), frappe.session.user, ())
    digest = get_commitment_digest(doc)
    doc.set("approval_critical_digest", digest)
    doc.set("approval_digest_version", DIGEST_VERSION)
    doc.set("approval_reviewer_user", frappe.session.user)
    doc.set("checked_by", employee)
    doc.set("checked_at", now_datetime())
    doc.set("checked_signature", signature)


def capture_authorization_snapshot(doc: Document) -> None:
    """Workflow task: sign final authorization for the current PO revision."""
    require_permission(doc, "write")
    _validate_supplier_selection(doc)
    employee, signature = _employee_snapshot()
    require_distinct_actors(
        str(doc.get("owner") or ""),
        frappe.session.user,
        previous_identities=(str(doc.get("approval_reviewer_user") or ""),),
    )
    if not doc.get("approval_critical_digest"):
        frappe.throw(_("Purchase Order review approval is required before final authorization."))
    if get_commitment_digest(doc) != doc.get("approval_critical_digest"):
        frappe.throw(_("Purchase Order approval is stale; return it for review again."))
    doc.set("approval_authorized_user", frappe.session.user)
    doc.set("authorized_by", employee)
    doc.set("authorized_at", now_datetime())
    doc.set("authorized_signature", signature)


def clear_approval_snapshots(doc: Document) -> None:
    """Workflow task: remove revision-bound evidence on return or correction."""
    if not doc.name or doc.docstatus != 0 or doc.get("workflow_state") != "Purchase Order Draft":
        frappe.throw(_("Purchase Order Return requires a saved draft transition."))
    persisted = frappe.db.get_value(
        "Purchase Order",
        doc.name,
        ["workflow_state", "docstatus", "owner", "approval_maker_user"],
        as_dict=True,
        for_update=True,
    )
    source = persisted.get("workflow_state") if persisted else None
    if not persisted or persisted.docstatus != 0 or source not in _RETURN_ROLES:
        frappe.throw(_("Purchase Order Return source is invalid."))
    maker = resolve_user(str(persisted.owner or ""))
    if (
        maker != resolve_user(str(persisted.approval_maker_user or ""))
        or maker != resolve_user(str(doc.get("owner") or ""))
        or maker != resolve_user(str(doc.get("approval_maker_user") or ""))
    ):
        frappe.throw(_("Purchase Order Maker changed during Return."))
    role = _RETURN_ROLES[cast(str, source)][0]
    actor = authorize_workflow_field_write(doc, _RETURN_ROUTE, _RETURN_ACTION, (role,))
    require_distinct_actors(maker, actor, ())
    for field in SNAPSHOT_FIELDS:
        doc.set(field, None)


def _return_action(doc: Document, source: str, expected_name: str | None = None) -> str:
    """Lock the single old open action and verify its original transition roles."""
    actions = frappe.db.sql(
        """select name, workflow_state from `tabWorkflow Action`
           where reference_doctype=%s and reference_name=%s and status='Open'
           for update""",
        (doc.doctype, doc.name),
        as_dict=True,
    )
    if len(actions) != 1 or actions[0].workflow_state != source:
        frappe.throw(_("Purchase Order Return requires one open source Workflow Action."))
    name = str(actions[0].name)
    if expected_name is not None and name != expected_name:
        frappe.throw(_("Purchase Order Return Workflow Action changed."))
    roles = frappe.db.sql(
        """select role from `tabWorkflow Action Permitted Role`
           where parent=%s and parenttype='Workflow Action' for update""",
        (name,),
        as_dict=True,
    )
    actual = [str(row.role) for row in roles]
    allowed = [_RETURN_ROLES[source][1]]
    if source == APPROVED_STATE:
        allowed.append({"Purchase Manager", "C-Level Approver"})
    if len(actual) != len(set(actual)) or set(actual) not in allowed:
        frappe.throw(_("Purchase Order Return Workflow Action roles changed."))
    return name


def _reject_critical_changes_after_review(doc: Document) -> None:
    previous = doc.get_doc_before_save()
    if not previous or previous.get("workflow_state") not in {APPROVAL_STATE, APPROVED_STATE}:
        return
    if doc.get("workflow_state") == "Purchase Order Draft" and previous.docstatus == doc.docstatus == 0:
        # Return must still compare every document value, while a lost File must not trap
        # independently authorized approvers in a reviewed state forever.
        before = _normalize_native_numbers(_normalize_native_temporals(_commitment_projection(previous)))
        after = _normalize_native_numbers(_normalize_native_temporals(_commitment_projection(doc)))
        if critical_digest(before) != critical_digest(after):
            frappe.throw(_("Commitment-critical Purchase Order fields cannot change after approval review."))
        return
    if get_commitment_digest(previous) != get_commitment_digest(doc):
        frappe.throw(_("Commitment-critical Purchase Order fields cannot change after approval review."))


def validate_workflow(doc: Document, method: str | None = None) -> None:
    """Reject commitment mutations after review and invalidate stale evidence."""
    del method
    _reject_critical_changes_after_review(doc)
    previous = doc.get_doc_before_save()
    if (
        not previous
        or previous.get("workflow_state") not in _RETURN_ROLES
        or doc.get("workflow_state") != "Purchase Order Draft"
    ):
        return
    consume_approval_field_grant(doc, _RETURN_ROUTE, _RETURN_ACTION)
    source = str(previous.get("workflow_state"))
    persisted = frappe.db.get_value(
        "Purchase Order",
        doc.name,
        ["workflow_state", "docstatus", "owner", "approval_maker_user"],
        as_dict=True,
        for_update=True,
    )
    if not persisted or persisted.workflow_state != source or persisted.docstatus != 0 or doc.docstatus != 0:
        frappe.throw(_("Purchase Order Return source changed."))
    maker = resolve_user(str(persisted.owner or ""))
    if any(
        resolve_user(str(value or "")) != maker
        for value in (
            persisted.approval_maker_user,
            previous.get("owner"),
            previous.get("approval_maker_user"),
            doc.get("owner"),
            doc.get("approval_maker_user"),
        )
    ):
        frappe.throw(_("Purchase Order Maker changed during Return."))
    if any(doc.get(field) for field in SNAPSHOT_FIELDS):
        frappe.throw(_("Purchase Order Return approval evidence must be cleared."))
    actor = resolve_user(str(frappe.session.user or ""))
    require_distinct_actors(maker, actor, ())
    role = _RETURN_ROLES[source][0]
    if role not in frappe.get_roles(actor):
        frappe.throw(_("Purchase Order Return role changed."))
    action_name = _return_action(doc, source)
    setattr(doc, _RETURN_PROOF, (source, action_name, maker, actor, role))
    authorize_workflow_field_write(doc, _RETURN_ROUTE, _RETURN_COMPLETION, (role,))


def complete_return_action(doc: Document, method: str | None = None) -> None:
    """Complete the old task after the PO row is saved, before native new task creation."""
    del method
    proof = getattr(doc, _RETURN_PROOF, None)
    if proof is None:
        return
    delattr(doc, _RETURN_PROOF)
    consume_approval_field_grant(doc, _RETURN_ROUTE, _RETURN_COMPLETION)
    source, action_name, maker, actor, role = proof
    previous = doc.get_doc_before_save()
    persisted = frappe.db.get_value(
        "Purchase Order",
        doc.name,
        ["workflow_state", "docstatus", "owner", "approval_maker_user"],
        as_dict=True,
        for_update=True,
    )
    if (
        not previous
        or previous.get("workflow_state") != source
        or not persisted
        or persisted.workflow_state != "Purchase Order Draft"
        or persisted.docstatus != 0
        or doc.get("workflow_state") != "Purchase Order Draft"
        or doc.docstatus != 0
        or resolve_user(str(frappe.session.user or "")) != actor
        or _RETURN_ROLES.get(source, (None,))[0] != role
        or any(
            resolve_user(str(value or "")) != maker
            for value in (
                persisted.owner,
                persisted.approval_maker_user,
                doc.get("owner"),
                doc.get("approval_maker_user"),
            )
        )
    ):
        frappe.throw(_("Purchase Order Return completion proof is invalid."))
    _return_action(doc, source, action_name)
    update_completed_workflow_actions_using_role(
        user=actor, workflow_action=[frappe._dict(name=action_name, role=role)]
    )


def _persisted_approval(doc: Document) -> Mapping[str, Any]:
    if not doc.name:
        frappe.throw(_("Purchase Order approval must be saved before submission."))
    row = frappe.db.get_value(
        "Purchase Order",
        doc.name,
        ["workflow_state", "owner", *SNAPSHOT_FIELDS],
        as_dict=True,
        for_update=True,
    )
    if not row:
        frappe.throw(_("Purchase Order approval could not be verified."))
    return cast(Mapping[str, Any], row)


def _execution_marker(doc: Document, action: str) -> dict[str, str]:
    return {
        "doctype": doc.doctype,
        "name": str(doc.name or ""),
        "action": action,
        "user": frappe.session.user,
    }


def _clear_execution_marker() -> None:
    setattr(frappe.flags, _EXECUTION_FLAG, None)


def authorize_submit_execution(doc: Document) -> None:
    """Workflow task: authorize this request's native Approved -> Submitted transition."""
    if not doc.name or doc.get("workflow_state") != SUBMITTED_STATE:
        frappe.throw(_("Purchase Order submit authorization requires the native Workflow transition."))
    setattr(frappe.flags, _EXECUTION_FLAG, _execution_marker(doc, "submit"))


def authorize_cancel_execution(doc: Document) -> None:
    """Workflow task: authorize this request's native Submitted -> Cancelled transition."""
    if not doc.name or doc.get("workflow_state") != CANCELLED_STATE:
        frappe.throw(_("Purchase Order cancel authorization requires the native Workflow transition."))
    setattr(frappe.flags, _EXECUTION_FLAG, _execution_marker(doc, "cancel"))


def validate_before_submit(doc: Document, method: str | None = None) -> None:
    """Fail closed before ERPNext's native Purchase Order submit effects."""
    del method
    try:
        marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
        if marker != _execution_marker(doc, "submit"):
            frappe.throw(_("Purchase Order must be submitted through its approved Workflow action."))
        require_permission(doc, "submit")
        _validate_supplier_selection(doc)
        persisted = _persisted_approval(doc)
        if persisted.get("workflow_state") != APPROVED_STATE or doc.get("workflow_state") != SUBMITTED_STATE:
            frappe.throw(_("Purchase Order must be approved through the native Workflow before submission."))
        if persisted.get("approval_digest_version") != DIGEST_VERSION:
            frappe.throw(_("Purchase Order approval version is invalid."))
        digest = get_commitment_digest(doc)
        if (
            persisted.get("approval_critical_digest") != digest
            or doc.get("approval_critical_digest") != digest
        ):
            frappe.throw(_("Purchase Order approval is stale; return it for review again."))
        owner = str(persisted.get("owner") or doc.get("owner") or "")
        reviewer = str(persisted.get("approval_reviewer_user") or "")
        approver = str(persisted.get("approval_authorized_user") or "")
        if (
            not reviewer
            or not approver
            or not persisted.get("checked_signature")
            or not persisted.get("authorized_signature")
        ):
            frappe.throw(
                _("Purchase Order requires signed review and final authorization before submission.")
            )
        require_distinct_actors(owner, reviewer, previous_identities=())
        require_distinct_actors(owner, approver, previous_identities=(reviewer,))
    finally:
        _clear_execution_marker()


def validate_before_cancel(doc: Document, method: str | None = None) -> None:
    """Prevent direct cancellation; native Workflow owns Submitted -> Cancelled."""
    del method
    try:
        marker = getattr(frappe.flags, _EXECUTION_FLAG, None)
        if marker != _execution_marker(doc, "cancel"):
            frappe.throw(_("Purchase Order must be cancelled through its Workflow action."))
        persisted_state = frappe.db.get_value(
            "Purchase Order",
            doc.name,
            "workflow_state",
            for_update=True,
        )
        if not (persisted_state == SUBMITTED_STATE and doc.get("workflow_state") == CANCELLED_STATE):
            frappe.throw(_("Submitted Purchase Orders must be cancelled through the native Workflow."))
    finally:
        _clear_execution_marker()
