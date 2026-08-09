# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Keep Connect Diagnostics navigation available in ERPNext Workspaces and sidebars."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

import frappe
from frappe.model.document import Document

NAVIGATION_LABEL = "Connect Diagnostics"
REGULATORY_WORKSPACE = "Connect Diagnostics Regulatory"
REGULATORY_MODULE = "Connect Diagnostics Regulatory"
STALE_PARENT_PAGE = ("Financial Reports", "Accounting")
RETIRED_SIDEBAR_LINKS = {
    "ERPNext Settings": frozenset({("DocType", "Repost Accounting Ledger Settings")}),
}


@dataclass(frozen=True)
class NavigationLink:
    """A DocType or Report shortcut managed in a Workspace and its sidebar."""

    label: str
    link_to: str
    link_type: Literal["DocType", "Report"]
    report_ref_doctype: str | None = None


@dataclass(frozen=True)
class NavigationGroup:
    """The ordered Connect Diagnostics shortcuts for one ERPNext module."""

    name: str
    links: tuple[NavigationLink, ...]


@dataclass(frozen=True)
class SidebarPlacement:
    """Where one managed link belongs in an existing module sidebar."""

    link_to: str
    after_link_to: str | None = None
    section: str | None = None
    icon: str = ""


REGULATORY_LINKS = (
    NavigationLink("Medical Device Product Registration", "Medical Device Product Registration", "DocType"),
    NavigationLink(
        "Medical Device Establishment Registration", "Medical Device Establishment Registration", "DocType"
    ),
    NavigationLink("Medical Device Regulatory Document", "Medical Device Regulatory Document", "DocType"),
    NavigationLink("Medical Device Registration Action", "Medical Device Registration Action", "DocType"),
    NavigationLink("Medical Device Regulatory Override", "Medical Device Regulatory Override", "DocType"),
    NavigationLink("Medical Device Regulatory Settings", "Medical Device Regulatory Settings", "DocType"),
    NavigationLink(
        "Medical Device Registration Expiry Summary",
        "Medical Device Registration Expiry Summary",
        "Report",
        "Medical Device Product Registration",
    ),
    NavigationLink(
        "Medical Device Item Coverage Matrix", "Medical Device Item Coverage Matrix", "Report", "Item"
    ),
    NavigationLink("Medical Device Compliance Gap", "Medical Device Compliance Gap", "Report", "Item"),
    NavigationLink(
        "Medical Device Regulatory Renewal Workbench",
        "Medical Device Regulatory Renewal Workbench",
        "Report",
        "Medical Device Registration Action",
    ),
    NavigationLink(
        "Medical Device Expiring Registration Affected Business",
        "Medical Device Expiring Registration Affected Business",
        "Report",
        "Medical Device Product Registration",
    ),
)


NAVIGATION_GROUPS = (
    NavigationGroup(
        name="Financial Reports",
        links=(
            NavigationLink("General Ledger TH", "General Ledger TH", "Report", "GL Entry"),
            NavigationLink("Trial Balance TH", "Trial Balance TH", "Report", "GL Entry"),
            NavigationLink("Trial Balance TH Detail", "Trial Balance TH Detail", "Report", "GL Entry"),
        ),
    ),
    NavigationGroup(
        name="Invoicing",
        links=(NavigationLink("Accounting Department", "Accounting Department", "DocType"),),
    ),
    NavigationGroup(
        name="Selling",
        links=(
            NavigationLink("Customer Credit Request", "Customer Credit Request", "DocType"),
            NavigationLink("DKSH Customer", "DKSH Customer", "DocType"),
            NavigationLink("Back Orders", "Back Orders", "Report", "Sales Order"),
            NavigationLink("Print Configuration Template", "Print Configuration Template", "DocType"),
            NavigationLink("Print Log", "Print Log", "DocType"),
        ),
    ),
    NavigationGroup(
        name="Stock",
        links=(
            NavigationLink("DKSH Item", "DKSH Item", "DocType"),
            NavigationLink("Product Group", "Product Group", "DocType"),
            NavigationLink("Regulation Class", "Regulation Class", "DocType"),
            NavigationLink("Storage Condition", "Storage Condition", "DocType"),
            NavigationLink("Back Orders", "Back Orders", "Report", "Sales Order"),
        ),
    ),
    NavigationGroup(
        name="Buying",
        links=(NavigationLink("Supplier Bank Change Request", "Supplier Bank Change Request", "DocType"),),
    ),
    NavigationGroup(
        name="ERPNext Settings",
        links=(
            NavigationLink("Department User Permission", "Department User Permission", "DocType"),
            NavigationLink("Backup Settings", "Backup Settings", "DocType"),
        ),
    ),
)

SIDEBAR_PLACEMENTS = {
    "Financial Reports": (
        SidebarPlacement("General Ledger TH", after_link_to="General Ledger", section="Ledgers"),
        SidebarPlacement("Trial Balance TH", after_link_to="Trial Balance", section="Financial Reports"),
        SidebarPlacement(
            "Trial Balance TH Detail", after_link_to="Trial Balance TH", section="Financial Reports"
        ),
    ),
    "Invoicing": (SidebarPlacement("Accounting Department", after_link_to="Account", icon="building-2"),),
    "Selling": (
        SidebarPlacement("Back Orders", after_link_to="Sales Order", icon="list-todo"),
        SidebarPlacement(
            "Customer Credit Request", after_link_to="Sales Invoice", icon="git-pull-request-arrow"
        ),
        SidebarPlacement("DKSH Customer", after_link_to="Customer", section="Setup"),
        SidebarPlacement(
            "Print Configuration Template",
            after_link_to="Sales Taxes and Charges Template",
            section="Setup",
        ),
        SidebarPlacement("Print Log", section="Reports"),
    ),
    "Stock": (
        SidebarPlacement("Back Orders", after_link_to="Pick List", icon="list-todo"),
        SidebarPlacement("DKSH Item", after_link_to="Item", section="Setup"),
        SidebarPlacement("Product Group", after_link_to="DKSH Item", section="Setup"),
        SidebarPlacement("Regulation Class", after_link_to="Product Group", section="Setup"),
        SidebarPlacement("Storage Condition", after_link_to="Regulation Class", section="Setup"),
    ),
    "Buying": (
        SidebarPlacement(
            "Supplier Bank Change Request",
            after_link_to="Purchase Invoice",
            icon="git-pull-request-arrow",
        ),
    ),
    "ERPNext Settings": (
        SidebarPlacement("Department User Permission", section="Other Settings"),
        SidebarPlacement(
            "Backup Settings", after_link_to="Department User Permission", section="Other Settings"
        ),
    ),
}


def ensure_workspace_navigation() -> None:
    """Maintain Connect Diagnostics cards and prioritized module sidebar sections."""
    ensure_regulatory_workspace()
    for group in NAVIGATION_GROUPS:
        workspace = frappe.get_doc("Workspace", group.name)
        workspace_changed = _repair_stale_parent_page(workspace)
        if _ensure_workspace_card(workspace, group):
            workspace_changed = True
        if workspace_changed:
            workspace.save(ignore_permissions=True)

        sidebar = frappe.get_doc("Workspace Sidebar", group.name)
        sidebar_changed = _remove_retired_sidebar_links(sidebar, group.name)
        if _ensure_sidebar_navigation(sidebar, group):
            sidebar_changed = True
        if sidebar_changed:
            _save_sidebar(sidebar)


def ensure_regulatory_workspace() -> None:
    """Create and maintain the independent Regulatory Workspace and its sidebar."""
    if not frappe.db.exists("Module Def", REGULATORY_MODULE):
        return
    if frappe.db.exists("Workspace", REGULATORY_WORKSPACE):
        workspace = frappe.get_doc("Workspace", REGULATORY_WORKSPACE)
    else:
        workspace = frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": REGULATORY_WORKSPACE,
                "title": REGULATORY_WORKSPACE,
                "module": REGULATORY_MODULE,
                "public": 1,
                "content": "[]",
            }
        )
    group = NavigationGroup(REGULATORY_WORKSPACE, REGULATORY_LINKS)
    changed = _ensure_workspace_card(workspace, group)
    if workspace.is_new():
        workspace.insert(ignore_permissions=True)
    elif changed:
        workspace.save(ignore_permissions=True)

    if frappe.db.exists("Workspace Sidebar", REGULATORY_WORKSPACE):
        sidebar = frappe.get_doc("Workspace Sidebar", REGULATORY_WORKSPACE)
    else:
        sidebar = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar",
                "title": REGULATORY_WORKSPACE,
                "module": REGULATORY_MODULE,
                "standard": 1,
                "app": "connect_diagnostics_core",
                "items": [],
            }
        )
    sidebar_changed = _ensure_regulatory_sidebar(sidebar)
    if sidebar.is_new():
        sidebar.insert(ignore_permissions=True)
    elif sidebar_changed:
        _save_sidebar(sidebar)


def _ensure_regulatory_sidebar(sidebar: Document) -> bool:
    rows = _rows(sidebar, "items")
    changed = False
    for link in REGULATORY_LINKS:
        values = {
            "type": "Link",
            "label": link.label,
            "link_type": link.link_type,
            "link_to": link.link_to,
            "child": 0,
            "collapsible": 1,
            "icon": "",
            "indent": 0,
            "keep_closed": 0,
            "show_arrow": 0,
        }
        row = _find_link(rows, link)
        if row is None:
            sidebar.append("items", values)
            changed = True
        elif _update_row(row, values):
            changed = True
    if changed:
        _reindex(rows)
    return changed


def _repair_stale_parent_page(workspace: Document) -> bool:
    workspace_name, stale_parent = STALE_PARENT_PAGE
    if workspace.name != workspace_name or workspace.get("parent_page") != stale_parent:
        return False
    if frappe.db.exists("Workspace", stale_parent):
        return False
    workspace.set("parent_page", "")
    return True


def _ensure_workspace_card(workspace: Document, group: NavigationGroup) -> bool:
    rows = _rows(workspace, "links")
    card_break = _find_card_break(rows)
    changed = False

    if card_break is None:
        workspace.append(
            "links",
            {
                "type": "Card Break",
                "label": NAVIGATION_LABEL,
                "link_count": 0,
            },
        )
        card_break = rows[-1]
        changed = True

    managed_rows = [card_break]
    for link in group.links:
        row = _find_link(rows, link)
        if row is None:
            workspace.append("links", _workspace_link_values(link))
            row = rows[-1]
            changed = True
        elif _update_row(row, _workspace_link_values(link)):
            changed = True
        managed_rows.append(row)

    if _order_workspace_card_rows(rows, managed_rows):
        changed = True

    if _ensure_card_block(workspace):
        changed = True

    return changed


def _find_card_break(rows: list[Document]) -> Document | None:
    return next(
        (row for row in rows if row.get("type") == "Card Break" and row.get("label") == NAVIGATION_LABEL),
        None,
    )


def _order_workspace_card_rows(rows: list[Document], managed_rows: list[Document]) -> bool:
    card_index = rows.index(managed_rows[0])
    managed_ids = {id(row) for row in managed_rows}
    insert_at = sum(id(row) not in managed_ids for row in rows[:card_index])
    remaining_rows = [row for row in rows if id(row) not in managed_ids]
    ordered_rows = [*remaining_rows[:insert_at], *managed_rows, *remaining_rows[insert_at:]]
    changed = any(current is not expected for current, expected in zip(rows, ordered_rows, strict=True))
    if not changed:
        return False
    rows[:] = ordered_rows
    for index, row in enumerate(rows, start=1):
        row.idx = index
    return True


def _workspace_link_values(link: NavigationLink) -> dict[str, str | int]:
    values: dict[str, str | int] = {
        "type": "Link",
        "label": link.label,
        "link_type": link.link_type,
        "link_to": link.link_to,
    }
    if link.link_type == "Report":
        values["is_query_report"] = 1
        values["report_ref_doctype"] = link.report_ref_doctype or ""
    return values


def _ensure_card_block(workspace: Document) -> bool:
    content = _content_blocks(workspace)
    if any(_is_card_block(block) for block in content):
        return False
    content.append({"type": "card", "data": {"card_name": NAVIGATION_LABEL, "col": 4}})
    workspace.set("content", json.dumps(content, separators=(",", ":")))
    return True


def _is_card_block(block: dict[str, object]) -> bool:
    data = block.get("data")
    if not isinstance(data, dict):
        return False
    card_data = cast(dict[str, object], data)
    return block.get("type") == "card" and card_data.get("card_name") == NAVIGATION_LABEL


def _content_blocks(workspace: Document) -> list[dict[str, object]]:
    raw_content = str(workspace.get("content") or "[]")
    content = json.loads(raw_content)
    if not isinstance(content, list):
        raise ValueError(f"Workspace {workspace.name} content must be a list.")
    if not all(isinstance(block, dict) for block in content):
        raise ValueError(f"Workspace {workspace.name} content must contain only objects.")
    return cast(list[dict[str, object]], content)


def _remove_retired_sidebar_links(sidebar: Document, sidebar_name: str) -> bool:
    retired_links = RETIRED_SIDEBAR_LINKS.get(sidebar_name, frozenset())
    if not retired_links:
        return False
    rows = _rows(sidebar, "items")
    retained_rows = [
        row
        for row in rows
        if (str(row.get("link_type") or ""), str(row.get("link_to") or "")) not in retired_links
    ]
    if len(retained_rows) == len(rows):
        return False
    rows[:] = retained_rows
    return True


def _ensure_sidebar_navigation(sidebar: Document, group: NavigationGroup) -> bool:
    rows = _rows(sidebar, "items")
    changed = _remove_managed_sidebar_section(rows)
    links = {link.link_to: link for link in group.links}

    for placement in SIDEBAR_PLACEMENTS[group.name]:
        link = links[placement.link_to]
        row = _find_link(rows, link)
        if row is None:
            sidebar.append("items", _sidebar_link_values(link, placement))
            row = rows[-1]
            changed = True
        elif _update_row(row, _sidebar_link_values(link, placement)):
            changed = True
        anchor = _find_sidebar_anchor(rows, group.name, placement)
        if _move_after(rows, row, anchor):
            changed = True

    if changed:
        _reindex(rows)
    return changed


def _remove_managed_sidebar_section(rows: list[Document]) -> bool:
    retained_rows = [
        row
        for row in rows
        if not (row.get("type") == "Section Break" and row.get("label") == NAVIGATION_LABEL)
    ]
    if len(retained_rows) == len(rows):
        return False
    rows[:] = retained_rows
    return True


def _find_link(rows: list[Document], link: NavigationLink) -> Document | None:
    return next(
        (
            row
            for row in rows
            if row.get("type") == "Link"
            and row.get("link_type") == link.link_type
            and row.get("link_to") == link.link_to
        ),
        None,
    )


def _sidebar_link_values(link: NavigationLink, placement: SidebarPlacement) -> dict[str, str | int]:
    return {
        "type": "Link",
        "label": link.label,
        "link_type": link.link_type,
        "link_to": link.link_to,
        "child": int(placement.section is not None),
        "collapsible": 1,
        "icon": "" if placement.section else placement.icon,
        "indent": 0,
        "keep_closed": 0,
        "show_arrow": 0,
    }


def _find_sidebar_anchor(rows: list[Document], sidebar_name: str, placement: SidebarPlacement) -> Document:
    if placement.section is None:
        anchor = next(
            (
                row
                for row in rows
                if row.get("type") == "Link" and row.get("link_to") == placement.after_link_to
            ),
            None,
        )
    else:
        section = next(
            (
                row
                for row in rows
                if row.get("type") == "Section Break" and row.get("label") == placement.section
            ),
            None,
        )
        if section is None:
            raise ValueError(f"Workspace Sidebar {sidebar_name} must contain section {placement.section}.")
        if placement.after_link_to is None:
            return section
        section_start = rows.index(section)
        section_end = next(
            (
                index
                for index, row in enumerate(rows[section_start + 1 :], start=section_start + 1)
                if not row.get("child")
            ),
            len(rows),
        )
        anchor = next(
            (
                row
                for row in rows[section_start + 1 : section_end]
                if row.get("type") == "Link" and row.get("link_to") == placement.after_link_to
            ),
            None,
        )

    if anchor is None:
        raise ValueError(f"Workspace Sidebar {sidebar_name} must contain anchor {placement.after_link_to}.")
    return anchor


def _move_after(rows: list[Document], row: Document, anchor: Document) -> bool:
    current_index = rows.index(row)
    rows.pop(current_index)
    target_index = rows.index(anchor) + 1
    rows.insert(target_index, row)
    return current_index != target_index


def _reindex(rows: list[Document]) -> None:
    for index, row in enumerate(rows, start=1):
        row.idx = index


def _update_row(row: Document, values: dict[str, str | int]) -> bool:
    if all(row.get(fieldname) == value for fieldname, value in values.items()):
        return False
    row.update(values)
    return True


def _save_sidebar(sidebar: Document) -> None:
    """Persist the site customization without exporting it into the ERPNext app."""
    previous_in_import = frappe.flags.in_import
    frappe.flags.in_import = True
    try:
        sidebar.save(ignore_permissions=True)
    finally:
        frappe.flags.in_import = previous_in_import


def _rows(document: Document, fieldname: str) -> list[Document]:
    rows = document.get(fieldname)
    return cast(list[Document], rows if rows is not None else [])
