# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Guard the one-row v5 Workflow revision around native fixture synchronization."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
from collections.abc import Iterator
from typing import Any, cast

import frappe
from frappe import _
from frappe.core.doctype.file.file import File
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils.password import get_encryption_key
from frappe.workflow.doctype.workflow.workflow import Workflow

from connect_diagnostics_core.patches.v1_0 import normalize_workflow_baseline as v4

RECOVERY_FILE = "connect-workflow-baseline-recovery-v5.json"
AUDIT_FILE = "connect-workflow-baseline-audit-v5.json"
CONSUMED_FILE = "connect-workflow-baseline-consumed-v5.json"
SNAPSHOT_VERSION = 5
PURCHASE_ORDER_WORKFLOW = "Connect Purchase Order Blueprint"
RETURN_TRANSITION = {
    "action": "Return Purchase Order",
    "allow_self_approval": 0,
    "allowed": "C-Level Approver",
    "condition": None,
    "state": "Purchase Order Approved",
    "next_state": "Purchase Order Draft",
    "transition_tasks": "Connect Purchase Order Approval Reset",
}
PAGE_SIZE = 500


def _fail(message: str) -> None:
    frappe.throw(_(message))


def _seal(artifact_id: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    envelope = {"site": frappe.local.site, "artifact_id": artifact_id, "kind": kind, "payload": payload}
    serialized = json.dumps(envelope, sort_keys=True, separators=(",", ":"))
    envelope["signature"] = hmac.new(
        get_encryption_key().encode(), serialized.encode(), hashlib.sha256
    ).hexdigest()
    return envelope


def _artifact(artifact_id: str, kind: str) -> dict[str, Any] | None:
    if not frappe.db.exists("File", artifact_id):
        return None
    record = cast(File, frappe.get_doc("File", artifact_id))
    stem = artifact_id.removesuffix(".json")
    if (
        record.name != artifact_id
        or not str(record.file_name or "").startswith(f"{stem}-")
        or not str(record.file_name or "").endswith(".json")
        or record.file_url != f"/private/files/{record.file_name}"
        or not record.is_private
    ):
        _fail("A v5 Workflow recovery artifact has an unexpected File identity or URL.")
    raw = record.get_content()
    if record.content_hash != get_content_hash(raw):
        _fail("A v5 Workflow recovery artifact has an invalid content hash.")
    try:
        envelope: dict[str, Any] = json.loads(raw)
        signature = str(envelope.pop("signature"))
        expected = _seal(artifact_id, kind, envelope["payload"])
    except (KeyError, TypeError, ValueError):
        _fail("A v5 Workflow recovery artifact has an invalid payload.")
    if envelope != {
        key: expected[key] for key in ("site", "artifact_id", "kind", "payload")
    } or not hmac.compare_digest(signature, expected["signature"]):
        _fail("A v5 Workflow recovery artifact failed site-bound authentication.")
    return envelope["payload"]


def _write_artifact(artifact_id: str, kind: str, payload: dict[str, Any]) -> None:
    if _artifact(artifact_id, kind) is not None:
        _fail("A v5 Workflow recovery artifact already exists.")
    frappe.get_doc(
        {
            "doctype": "File",
            "file_name": f"{artifact_id.removesuffix('.json')}-{frappe.generate_hash(length=12)}.json",
            "is_private": 1,
            "content": json.dumps(_seal(artifact_id, kind, payload), sort_keys=True),
        }
    ).insert(ignore_permissions=True, set_name=artifact_id)
    if _artifact(artifact_id, kind) != payload:
        _fail("A v5 Workflow recovery artifact did not persist as expected.")


def _current_blueprint() -> dict[str, dict[str, Any]]:
    archived, _, _ = v4._blueprint()
    current = copy.deepcopy(archived)
    po = current[PURCHASE_ORDER_WORKFLOW]
    transitions = po["transitions"]
    post_indexes = [
        index for index, row in enumerate(transitions) if row.get("action") == "Post Purchase Order"
    ]
    if len(post_indexes) != 1 or RETURN_TRANSITION in transitions:
        _fail("The archived v4 Purchase Order transitions differ from the reviewed v5 predecessor.")
    transitions.insert(post_indexes[0], copy.deepcopy(RETURN_TRANSITION))
    return current


def _locked_config() -> None:
    for name in sorted(v4.CANONICAL_WORKFLOWS):
        frappe.db.get_value("Workflow", name, "name", for_update=True)


def _rows(doctype: str, filters: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    last_name = ""
    while True:
        page_filters = dict(filters or {})
        if last_name:
            page_filters["name"] = [">", last_name]
        page = frappe.get_all(
            doctype,
            filters=page_filters,
            fields=["*"],
            order_by="name asc",
            limit_page_length=PAGE_SIZE,
        )
        if not page:
            return
        for row in page:
            yield dict(row)
        next_name = str(page[-1].name)
        if next_name <= last_name:
            _fail("Workflow history pagination did not advance.")
        last_name = next_name
        if len(page) < PAGE_SIZE:
            return


def _fingerprint(rows: Iterator[dict[str, Any]]) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True, default=str, separators=(",", ":")).encode())
        digest.update(b"\n")
        count += 1
    return {"count": count, "sha256": digest.hexdigest()}


def _history() -> dict[str, Any]:
    business = {
        doctype: _fingerprint(_rows(doctype)) for doctype in sorted(set(v4.CANONICAL_WORKFLOWS.values()))
    }
    return {
        "business": business,
        "actions": _fingerprint(_rows("Workflow Action")),
        "action_roles": _fingerprint(_rows("Workflow Action Permitted Role")),
        "business_versions": _fingerprint(
            _rows("Version", {"ref_doctype": ["in", sorted(set(v4.CANONICAL_WORKFLOWS.values()))]})
        ),
    }


def _configuration_versions() -> dict[str, Any]:
    return _fingerprint(
        _rows(
            "Version",
            {
                "ref_doctype": [
                    "in",
                    ["Workflow", "Workflow State", "Workflow Action Master", "Workflow Transition Tasks"],
                ]
            },
        )
    )


def _check_actions(current: dict[str, dict[str, Any]]) -> None:
    by_doctype = {doctype: name for name, doctype in v4.CANONICAL_WORKFLOWS.items()}
    canonical_action_names: set[str] = set()
    for action in _rows("Workflow Action"):
        doctype = str(action.get("reference_doctype") or "")
        if doctype not in by_doctype:
            continue
        canonical_action_names.add(str(action["name"]))
        reference_name = str(action.get("reference_name") or "")
        if not frappe.db.exists(doctype, reference_name):
            _fail("A Workflow Action references a missing canonical business document.")
        workflow = current[by_doctype[doctype]]
        states = {str(row["state"]) for row in workflow["states"]}
        state = str(action.get("workflow_state") or "")
        if state not in states or action.get("status") not in {"Open", "Completed"}:
            _fail("A Workflow Action has an unknown state or status.")
        if action.get("status") == "Open":
            document_state = frappe.db.get_value(doctype, reference_name, "workflow_state")
            if document_state != state:
                _fail("An open Workflow Action conflicts with its business state.")
    for role in _rows("Workflow Action Permitted Role"):
        if role.get("parenttype") != "Workflow Action" or role.get("parentfield") != "permitted_roles":
            _fail("A Workflow Action role has an invalid parent reference.")
        parent = str(role.get("parent") or "")
        if parent in canonical_action_names:
            continue
        if not frappe.db.exists("Workflow Action", parent):
            _fail("A Workflow Action role has a dangling parent reference.")


def _site_shape(current: dict[str, dict[str, Any]]) -> str:
    archived, states, actions = v4._blueprint()
    groups = v4._task_blueprints(archived)
    v4._assert_snapshot_revision(archived, states, actions, groups)
    shape = "absent"
    present: set[str] = set()
    for name, doctype in v4.CANONICAL_WORKFLOWS.items():
        active = set(frappe.get_all("Workflow", {"document_type": doctype, "is_active": 1}, pluck="name"))
        if active - {name}:
            _fail("An active Workflow collision exists for a canonical document type.")
        if not frappe.db.exists("Workflow", name):
            if active:
                _fail("A canonical Workflow is absent while another route is active.")
            continue
        present.add(name)
        live = frappe.get_doc("Workflow", name)
        if v4.workflow_shape(live) == v4.workflow_shape(archived[name]):
            observed = "v4"
        elif v4.workflow_shape(live) == v4.workflow_shape(current[name]):
            observed = "v5"
        else:
            _fail("A canonical Workflow differs from both reviewed revisions.")
        if name == PURCHASE_ORDER_WORKFLOW:
            shape = observed
        elif observed != "v4":
            _fail("A non-Purchase-Order Workflow differs from the archived v4 baseline.")
    if present and present != set(archived):
        _fail("The canonical Workflow set is incomplete.")
    for doctype, records in (("Workflow State", states), ("Workflow Action Master", actions)):
        for name, record in records.items():
            if frappe.db.exists(doctype, name) and v4._master_shape(
                frappe.get_doc(doctype, name), doctype
            ) != v4._master_shape(record, doctype):
                _fail("A Workflow companion differs from the reviewed v4 contract.")
    for name, rows in groups.items():
        if frappe.db.exists(
            "Workflow Transition", {"transition_tasks": name, "parent": ["not in", list(archived)]}
        ):
            _fail("A Workflow callback group has a foreign reference.")
        if (
            frappe.db.exists("Workflow Transition Tasks", name)
            and v4._task_rows(frappe.get_doc("Workflow Transition Tasks", name)) != rows
        ):
            _fail("A Workflow callback group differs from the reviewed v4 contract.")
    for doctype, definitions in v4.CUSTOM_FIELDS.items():
        for definition in definitions:
            existing = frappe.db.get_value(
                "Custom Field",
                {"dt": doctype, "fieldname": definition["fieldname"]},
                list(definition),
                as_dict=True,
            )
            if existing and any(
                (existing.get(key) or None) != (value or None) for key, value in definition.items()
            ):
                _fail("A Workflow Custom Field differs from the archived v4 contract.")
    for name, doctype in v4.CANONICAL_WORKFLOWS.items():
        states_by_name = {str(row["state"]): int(row["doc_status"]) for row in current[name]["states"]}
        for row in v4._business_rows(doctype):
            if states_by_name.get(row["workflow_state"]) != row["docstatus"]:
                _fail("A business document has an invalid Workflow state or docstatus.")
        if shape == "absent" and (frappe.db.count(doctype) or list(v4._action_rows(doctype))):
            _fail("A canonical Workflow is absent while business history exists.")
    _check_actions(current)
    return shape


def _snapshot() -> dict[str, Any] | None:
    consumed = _artifact(CONSUMED_FILE, "consumed")
    if consumed is not None:
        if consumed != {"schema_version": SNAPSHOT_VERSION, "status": "rolled_back"}:
            _fail("The v5 Workflow consumed marker has an invalid shape.")
        _fail(
            "The v5 Workflow recovery was consumed; restore the reviewed v4 source bundle before migration."
        )
    saved = _artifact(RECOVERY_FILE, "recovery")
    if saved is None:
        return None
    if saved.get("schema_version") != SNAPSHOT_VERSION:
        _fail("The v5 Workflow recovery snapshot has an invalid schema version.")
    if saved.get("status") != "active" or saved.get("predecessor") not in {"absent", "v4"}:
        _fail("The v5 Workflow recovery snapshot has an invalid status.")
    if not isinstance(saved.get("desired_hashes"), dict) or not isinstance(saved.get("history"), dict):
        _fail("The v5 Workflow recovery snapshot has an invalid shape.")
    return saved


def preflight() -> None:
    """Read-only gate before install/migrate; admit absent, exact v4, or exact v5."""
    current = _current_blueprint()
    shape = _site_shape(current)
    saved = _snapshot()
    if saved:
        if saved["desired_hashes"] != {name: v4.workflow_fingerprint(row) for name, row in current.items()}:
            _fail("The v5 Workflow recovery snapshot differs from the reviewed revision.")
        audit = _artifact(AUDIT_FILE, "audit")
        if audit is not None and (
            audit.get("schema_version") != SNAPSHOT_VERSION
            or audit.get("desired_hashes") != saved["desired_hashes"]
            or not isinstance(audit.get("config_versions"), dict)
        ):
            _fail("The v5 Workflow completion audit differs from the reviewed revision.")
        if audit is None and saved["history"] != _history():
            _fail("Business or Workflow Action history changed during the v5 configuration window.")
        if shape == "absent" or (shape == "v4" and (saved["predecessor"] != "v4" or audit is not None)):
            _fail("The v5 Workflow snapshot conflicts with installed configuration.")
    elif shape == "v5":
        _fail("The v5 Workflow is installed without its recovery snapshot.")


def _create_snapshot(predecessor: str, current: dict[str, dict[str, Any]]) -> None:
    payload = {
        "schema_version": SNAPSHOT_VERSION,
        "status": "active",
        "predecessor": predecessor,
        "desired_hashes": {name: v4.workflow_fingerprint(row) for name, row in current.items()},
        "history": _history(),
        "config_versions_before": _configuration_versions(),
    }
    _write_artifact(RECOVERY_FILE, "recovery", payload)


def prepare() -> None:
    """After install, record the clean predecessor before native fixture import."""
    _locked_config()
    preflight()
    if _snapshot() is None:
        _create_snapshot(_site_shape(_current_blueprint()), _current_blueprint())


def execute() -> None:
    """Patch existing v4 PO before fixture import, which may skip older modified stamps."""
    _locked_config()
    preflight()
    current = _current_blueprint()
    shape = _site_shape(current)
    if _snapshot() is None:
        _create_snapshot(shape, current)
    if shape == "absent" or shape == "v5":
        return
    po = cast(Workflow, frappe.get_doc("Workflow", PURCHASE_ORDER_WORKFLOW))
    post_index = next(
        index for index, row in enumerate(po.transitions) if row.action == "Post Purchase Order"
    )
    inserted = po.append("transitions", RETURN_TRANSITION)
    po.transitions.remove(inserted)
    po.transitions.insert(post_index, inserted)
    for index, row in enumerate(po.transitions, 1):
        row.idx = index
    po.save(ignore_permissions=True)
    if v4.workflow_shape(po) != v4.workflow_shape(current[PURCHASE_ORDER_WORKFLOW]):
        _fail("The Purchase Order Workflow did not reach the reviewed v5 shape.")


def verify() -> None:
    """Verify native fixture sync and the unchanged business/action evidence."""
    _locked_config()
    preflight()
    if _site_shape(_current_blueprint()) != "v5":
        _fail("The v5 Workflow fixture has not synchronized to the reviewed shape.")
    saved = _snapshot()
    if saved and _artifact(AUDIT_FILE, "audit") is None:
        _write_artifact(
            AUDIT_FILE,
            "audit",
            {
                "schema_version": SNAPSHOT_VERSION,
                "desired_hashes": saved["desired_hashes"],
                "config_versions": _configuration_versions(),
            },
        )
