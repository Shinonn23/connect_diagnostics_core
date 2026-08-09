# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Seed Print Configuration Template rows from the print document registry."""

from __future__ import annotations

from typing import Any, cast

import frappe
from frappe.model.document import Document

from connect_diagnostics_core.setup import print_documents

DEFAULT_TEMPLATE = "Default"

# The three document policies the Customer base actually uses, named after what
# they print rather than after a Customer Group, because more than one group
# follows each. Values are the initial contents only: a Template is user data
# from then on, so an edit is never overwritten.
POLICY_TEMPLATES: dict[str, dict[str, dict[str, Any]]] = {
    "Tax Invoice Only": {
        "receipt": {"enabled": 0},
        "abbreviated_tax_invoice": {"enabled": 0},
        "__all__": {"show_date": 1},
    },
    "Tax Invoice and Receipt": {
        "receipt": {"enabled": 1},
        "abbreviated_tax_invoice": {"enabled": 0},
        "__all__": {"show_date": 0},
    },
    "Tax Invoice and Abbreviated Receipt": {
        "receipt": {"enabled": 0},
        "abbreviated_tax_invoice": {"enabled": 1},
        "__all__": {"show_date": 1},
    },
}

EVERY_DOCUMENT = "__all__"


def ensure_policy_templates() -> None:
    """Create the document policy Templates, leaving existing ones untouched."""
    for template_name, policy in POLICY_TEMPLATES.items():
        if frappe.db.exists("Print Configuration Template", template_name):
            continue

        template = frappe.new_doc("Print Configuration Template")
        template.update({"template_name": template_name})
        seed_registry_rows(template)
        _apply_policy(template, policy)
        template.insert(ignore_permissions=True)


def _apply_policy(template: Document, policy: dict[str, dict[str, Any]]) -> None:
    """Set the policy's values on the freshly seeded document rows."""
    shared = policy.get(EVERY_DOCUMENT, {})
    for row in template.get("print_documents") or []:
        for fieldname, value in shared.items():
            row.set(fieldname, value)
        for fieldname, value in policy.get(str(row.get("document_key")), {}).items():
            row.set(fieldname, value)


def ensure_default_template() -> None:
    """Create the Default Template, or top it up with newly registered documents."""
    if not frappe.db.exists("Print Configuration Template", DEFAULT_TEMPLATE):
        template = frappe.new_doc("Print Configuration Template")
        template.update({"template_name": DEFAULT_TEMPLATE})
        seed_registry_rows(template)
        template.insert(ignore_permissions=True)
        return

    template = cast(Document, frappe.get_doc("Print Configuration Template", DEFAULT_TEMPLATE))
    if seed_registry_rows(template):
        template.save(ignore_permissions=True)


def seed_registry_rows(parent: Document) -> bool:
    """Add a row for every registered document and copy the parent is missing.

    Existing rows are never overwritten, so a Template edited by a user keeps its
    values while still gaining rows for documents added to the registry later.
    Returns True when anything was added.
    """
    existing_documents = {_text(row.get("document_key")) for row in _rows(parent, "print_documents")}
    existing_copies = {
        (_text(row.get("document_key")), _text(row.get("copy_key"))) for row in _rows(parent, "print_copies")
    }
    added = False

    for document in print_documents.PRINT_DOCUMENTS:
        if document.key not in existing_documents:
            parent.append(
                "print_documents",
                {
                    "document_key": document.key,
                    "document_label": document.label,
                    "enabled": 1,
                    "show_date": 1,
                    "language": print_documents.default_language(document),
                    "show_batch_serial": 1 if document.offers_batch_serial else 0,
                },
            )
            added = True

        for definition in document.copies:
            if (document.key, definition.key) in existing_copies:
                continue
            parent.append(
                "print_copies",
                {
                    "document_key": document.key,
                    "copy_key": definition.key,
                    "label": definition.label_th,
                    "kind": definition.kind,
                    "count": definition.default_count,
                },
            )
            added = True

    return added


def _rows(parent: Document, fieldname: str) -> list[dict[str, Any]]:
    return [row.as_dict() for row in (parent.get(fieldname) or [])]


def _text(value: Any) -> str:
    return str(value or "").strip()
