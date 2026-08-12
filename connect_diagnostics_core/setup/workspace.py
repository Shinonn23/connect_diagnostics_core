# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Keep Connect Diagnostics navigation available in ERPNext Workspaces and sidebars."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

import frappe
from frappe.model.document import Document

NAVIGATION_LABEL = "Connect Diagnostics"
# Public Desk label for the regulatory domain. Keep the module name internal so
# existing DocType ownership and permissions remain backward compatible.
REGULATORY_WORKSPACE = "Regulatory"
REGULATORY_MODULE = "Connect Diagnostics Regulatory"
LEGACY_REGULATORY_WORKSPACE = "Connect Diagnostics Regulatory"
REGULATORY_ICON = "shield-check"
REGULATORY_SIDEBAR_MIGRATION_FLAG = "_regulatory_sidebar_custom_rows"
REGULATORY_WORKSPACE_MIGRATION_FLAG = "_regulatory_workspace_custom_rows"
WORKSPACE_LINK_FIELDS = (
    "type",
    "label",
    "icon",
    "hidden",
    "link_type",
    "link_to",
    "dependencies",
    "only_for",
    "onboard",
    "is_query_report",
    "report_ref_doctype",
    "link_count",
    "description",
)
WORKSPACE_LINK_KEY_FIELDS = ("type", "label", "link_type", "link_to")
WORKSPACE_CHILD_TABLE_FIELDS = (
    "charts",
    "shortcuts",
    "quick_lists",
    "number_cards",
    "custom_blocks",
    "roles",
)
SIDEBAR_ITEM_FIELDS = (
    "type",
    "label",
    "link_type",
    "link_to",
    "icon",
    "child",
    "navigate_to_tab",
    "collapsible",
    "indent",
    "keep_closed",
    "show_arrow",
    "url",
    "filters",
    "route_options",
)
STALE_PARENT_PAGE = ("Financial Reports", "Accounting")
RETIRED_SIDEBAR_LINKS = {
    "ERPNext Settings": frozenset(
        {
            ("DocType", "Repost Accounting Ledger Settings"),
            ("DocType", "Department User Permission"),
        }
    ),
    "Financial Reports": frozenset(
        {
            ("Report", "General Ledger TH"),
            ("Report", "Trial Balance TH"),
            ("Report", "Trial Balance TH Detail"),
        }
    ),
}
RETIRED_CARD_LINKS: dict[str, frozenset[tuple[str, str]]] = {
    "ERPNext Settings": frozenset({("DocType", "Department User Permission")}),
    "Financial Reports": frozenset(
        {
            ("Report", "General Ledger TH"),
            ("Report", "Trial Balance TH"),
            ("Report", "Trial Balance TH Detail"),
        }
    ),
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


REGULATORY_WORKSPACE_GROUPS = (
    NavigationGroup(
        name="Main",
        links=(
            NavigationLink("Product Registration", "Medical Device Product Registration", "DocType"),
            NavigationLink("Regulatory Document", "Medical Device Regulatory Document", "DocType"),
            NavigationLink("Registration Action", "Medical Device Registration Action", "DocType"),
            NavigationLink("Override", "Medical Device Regulatory Override", "DocType"),
        ),
    ),
    NavigationGroup(
        name="Reports",
        links=(
            NavigationLink(
                "Expiry Summary",
                "Medical Device Registration Expiry Summary",
                "Report",
                "Medical Device Product Registration",
            ),
            NavigationLink("Coverage Matrix", "Medical Device Item Coverage Matrix", "Report", "Item"),
            NavigationLink("Compliance Gaps", "Medical Device Compliance Gap", "Report", "Item"),
            NavigationLink(
                "Renewal Workbench",
                "Medical Device Regulatory Renewal Workbench",
                "Report",
                "Medical Device Registration Action",
            ),
            NavigationLink(
                "Affected Business",
                "Medical Device Expiring Registration Affected Business",
                "Report",
                "Medical Device Product Registration",
            ),
        ),
    ),
    NavigationGroup(
        name="Setup",
        links=(
            NavigationLink(
                "Establishment Registration",
                "Medical Device Establishment Registration",
                "DocType",
            ),
        ),
    ),
    NavigationGroup(
        name="Settings",
        links=(NavigationLink("Regulatory Settings", "Medical Device Regulatory Settings", "DocType"),),
    ),
)
REGULATORY_LINKS = tuple(link for group in REGULATORY_WORKSPACE_GROUPS for link in group.links)


# Stock Count's counting + two-tier approval workflow is a distinct operating loop
# from day-to-day Stock (see the workspace-navigation rule in CLAUDE.md), so it gets
# its own independent Workspace instead of crowding the existing Stock Workspace.
# General stock reports/masters (Storage Location, expiry, goods receipt) stay in
# the existing Stock Workspace since they are not specific to counting.
STOCK_COUNT_WORKSPACE = "Stock Counting"
# Deliberately not "Stock Count": Frappe's route-conflict check slugifies every Page,
# Workspace, and DocType name and rejects duplicates, and the "Stock Count" DocType
# already owns that slug -- see `frappe.desk.utils.validate_route_conflict`.
STOCK_COUNT_MODULE = "Connect Diagnostics Stock"
STOCK_COUNT_ICON = "clipboard-list"

STOCK_COUNT_WORKSPACE_GROUPS = (
    NavigationGroup(
        name="Main",
        links=(NavigationLink("Stock Count", "Stock Count", "DocType"),),
    ),
    NavigationGroup(
        name="Reports",
        links=(NavigationLink("Variance Summary", "Stock Count Variance", "Report", "Stock Count"),),
    ),
)


NAVIGATION_GROUPS = (
    NavigationGroup(
        name="Financial Reports",
        links=(),
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
            NavigationLink("Storage Location", "Storage Location", "DocType"),
            NavigationLink("Back Orders", "Back Orders", "Report", "Sales Order"),
            NavigationLink("Short Expiry Report", "Short Expiry Report", "Report", "Item"),
            NavigationLink("Goods Receipt Report", "Goods Receipt Report", "Report", "Purchase Receipt"),
        ),
    ),
    NavigationGroup(
        name="Buying",
        links=(NavigationLink("Supplier Bank Change Request", "Supplier Bank Change Request", "DocType"),),
    ),
    NavigationGroup(
        name="ERPNext Settings",
        links=(NavigationLink("Backup Settings", "Backup Settings", "DocType"),),
    ),
    NavigationGroup(
        name="HR Setup",
        links=(NavigationLink("Accounting Department", "Accounting Department", "DocType"),),
    ),
    NavigationGroup(
        name="Payroll",
        links=(NavigationLink("Accounting Department", "Accounting Department", "DocType"),),
    ),
)

SIDEBAR_PLACEMENTS = {
    "Financial Reports": (),
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
        SidebarPlacement("Short Expiry Report", after_link_to="Back Orders", icon="calendar-clock"),
        SidebarPlacement("Goods Receipt Report", after_link_to="Short Expiry Report", icon="package-check"),
        SidebarPlacement("DKSH Item", after_link_to="Item", section="Setup"),
        SidebarPlacement("Product Group", after_link_to="DKSH Item", section="Setup"),
        SidebarPlacement("Regulation Class", after_link_to="Product Group", section="Setup"),
        SidebarPlacement("Storage Condition", after_link_to="Regulation Class", section="Setup"),
        SidebarPlacement("Storage Location", after_link_to="Storage Condition", section="Setup"),
    ),
    "Buying": (
        SidebarPlacement(
            "Supplier Bank Change Request",
            after_link_to="Purchase Invoice",
            icon="git-pull-request-arrow",
        ),
    ),
    "ERPNext Settings": (SidebarPlacement("Backup Settings", section="Other Settings"),),
    "HR Setup": (SidebarPlacement("Accounting Department", after_link_to="Department", section="Setup"),),
    "Payroll": (
        SidebarPlacement("Accounting Department", after_link_to="Salary Structure", section="Setup"),
    ),
}


def ensure_workspace_navigation() -> None:
    """Maintain Connect Diagnostics cards and prioritized module sidebar sections."""
    ensure_regulatory_workspace()
    ensure_stock_count_workspace()
    for group in NAVIGATION_GROUPS:
        workspace = frappe.get_doc("Workspace", group.name)
        workspace_changed = _repair_stale_parent_page(workspace)
        if _remove_retired_card_links(workspace, group.name):
            workspace_changed = True
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
    _migrate_legacy_regulatory_navigation()
    if frappe.db.exists("Workspace", REGULATORY_WORKSPACE):
        workspace = frappe.get_doc("Workspace", REGULATORY_WORKSPACE)
    else:
        workspace = frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": REGULATORY_WORKSPACE,
                "title": REGULATORY_WORKSPACE,
                "module": REGULATORY_MODULE,
                "icon": REGULATORY_ICON,
                "public": 1,
                "content": "[]",
            }
        )
    changed = False
    if workspace.get("icon") != REGULATORY_ICON:
        workspace.set("icon", REGULATORY_ICON)
        changed = True
    if _ensure_regulatory_workspace_cards(workspace):
        changed = True
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
                "header_icon": REGULATORY_ICON,
                "standard": 1,
                "app": "connect_diagnostics_core",
                "items": [],
            }
        )
    sidebar_changed = _ensure_regulatory_sidebar(sidebar)
    if sidebar.get("header_icon") != REGULATORY_ICON:
        sidebar.set("header_icon", REGULATORY_ICON)
        sidebar_changed = True
    if sidebar.is_new():
        sidebar.insert(ignore_permissions=True)
    elif sidebar_changed:
        _save_sidebar(sidebar)


def ensure_stock_count_workspace() -> None:
    """Create and maintain the independent Stock Count Workspace and its sidebar.

    Unlike Regulatory, there is no pre-existing site to migrate: this workspace
    and sidebar are wholly app-owned from creation, so a full-replace comparison
    (rebuild the managed rows, save only if they differ) is sufficient -- no
    partial reconciliation with unmanaged customizations is needed.
    """
    if frappe.db.exists("Workspace", STOCK_COUNT_WORKSPACE):
        workspace = frappe.get_doc("Workspace", STOCK_COUNT_WORKSPACE)
    else:
        workspace = frappe.get_doc(
            {
                "doctype": "Workspace",
                "label": STOCK_COUNT_WORKSPACE,
                "title": STOCK_COUNT_WORKSPACE,
                "module": STOCK_COUNT_MODULE,
                "icon": STOCK_COUNT_ICON,
                "public": 1,
                "content": "[]",
            }
        )

    changed = False
    if workspace.get("icon") != STOCK_COUNT_ICON:
        workspace.set("icon", STOCK_COUNT_ICON)
        changed = True

    desired_links: list[dict[str, str | int]] = []
    for group in STOCK_COUNT_WORKSPACE_GROUPS:
        desired_links.append({"type": "Card Break", "label": group.name, "link_count": 0})
        desired_links.extend(_workspace_link_values(link) for link in group.links)
    current_links = _rows(workspace, "links")
    if len(current_links) != len(desired_links) or not all(
        _workspace_row_matches(row, values) for row, values in zip(current_links, desired_links, strict=False)
    ):
        workspace.set("links", [])
        for values in desired_links:
            workspace.append("links", values)
        _reindex(_rows(workspace, "links"))
        changed = True

    desired_content = [
        {"type": "card", "data": {"card_name": group.name, "col": 4}}
        for group in STOCK_COUNT_WORKSPACE_GROUPS
    ]
    if _content_blocks(workspace) != desired_content:
        workspace.set("content", json.dumps(desired_content, separators=(",", ":")))
        changed = True

    if workspace.is_new():
        workspace.insert(ignore_permissions=True)
    elif changed:
        workspace.save(ignore_permissions=True)

    _ensure_stock_count_sidebar()


def _ensure_stock_count_sidebar() -> None:
    if frappe.db.exists("Workspace Sidebar", STOCK_COUNT_WORKSPACE):
        sidebar = frappe.get_doc("Workspace Sidebar", STOCK_COUNT_WORKSPACE)
    else:
        sidebar = frappe.get_doc(
            {
                "doctype": "Workspace Sidebar",
                "title": STOCK_COUNT_WORKSPACE,
                "module": STOCK_COUNT_MODULE,
                "header_icon": STOCK_COUNT_ICON,
                "standard": 1,
                "app": "connect_diagnostics_core",
                "items": [],
            }
        )

    desired_items = _stock_count_sidebar_items()
    current_items = _rows(sidebar, "items")
    changed = sidebar.get("header_icon") != STOCK_COUNT_ICON
    if changed:
        sidebar.set("header_icon", STOCK_COUNT_ICON)
    if len(current_items) != len(desired_items) or not all(
        _sidebar_row_matches(row, values) for row, values in zip(current_items, desired_items, strict=False)
    ):
        sidebar.set("items", [])
        for values in desired_items:
            sidebar.append("items", values)
        _reindex(_rows(sidebar, "items"))
        changed = True

    if sidebar.is_new():
        sidebar.insert(ignore_permissions=True)
    elif changed:
        _save_sidebar(sidebar)


def _stock_count_sidebar_items() -> list[dict[str, str | int]]:
    items: list[dict[str, str | int]] = [
        {
            "type": "Link",
            "label": "Home",
            "link_type": "Workspace",
            "link_to": STOCK_COUNT_WORKSPACE,
            "child": 0,
            "collapsible": 1,
            "icon": "home",
            "indent": 0,
            "keep_closed": 0,
            "show_arrow": 0,
        }
    ]
    main_group, reports_group = STOCK_COUNT_WORKSPACE_GROUPS
    items.extend(
        {
            "type": "Link",
            "label": link.label,
            "link_type": link.link_type,
            "link_to": link.link_to,
            "child": 0,
            "collapsible": 1,
            "icon": STOCK_COUNT_ICON,
            "indent": 0,
            "keep_closed": 0,
            "show_arrow": 0,
            **(
                {"is_query_report": 1, "report_ref_doctype": link.report_ref_doctype or ""}
                if link.link_type == "Report"
                else {}
            ),
        }
        for link in main_group.links
    )
    items.append(
        {
            "type": "Section Break",
            "label": reports_group.name,
            "link_type": "DocType",
            "child": 0,
            "collapsible": 1,
            "icon": "sheet",
            "indent": 1,
        }
    )
    items.extend(
        {
            "type": "Link",
            "label": link.label,
            "link_type": link.link_type,
            "link_to": link.link_to,
            "child": 1,
            "collapsible": 1,
            "icon": "",
            "indent": 0,
            "keep_closed": 0,
            "show_arrow": 0,
            **(
                {"is_query_report": 1, "report_ref_doctype": link.report_ref_doctype or ""}
                if link.link_type == "Report"
                else {}
            ),
        }
        for link in reports_group.links
    )
    return items


def snapshot_regulatory_sidebar_customizations() -> None:
    """Capture unmanaged public sidebar rows before app-level JSON sync runs.

    Frappe imports standard ``workspace_sidebar`` JSON before ``after_migrate``.
    Keeping the rows in request-local flags lets the post-migration reconciler
    restore user-added links and sections if the standard file was updated.
    """
    snapshots: dict[str, list[dict[str, object]]] = {}
    for sidebar_name in (REGULATORY_WORKSPACE, LEGACY_REGULATORY_WORKSPACE):
        if not frappe.db.exists("Workspace Sidebar", sidebar_name):
            continue
        sidebar = frappe.get_doc("Workspace Sidebar", sidebar_name)
        rows = _rows(sidebar, "items")
        managed_indexes = _regulatory_sidebar_managed_indexes(rows)
        custom_rows = [
            _sidebar_row_values(row) for index, row in enumerate(rows) if index not in managed_indexes
        ]
        if custom_rows:
            snapshots[sidebar_name] = custom_rows
    setattr(frappe.flags, REGULATORY_SIDEBAR_MIGRATION_FLAG, snapshots)


def snapshot_regulatory_workspace_customizations() -> None:
    """Capture unmanaged workspace rows before orphan cleanup runs."""
    snapshots: dict[str, dict[str, object]] = {}
    for workspace_name in (REGULATORY_WORKSPACE, LEGACY_REGULATORY_WORKSPACE):
        if not frappe.db.exists("Workspace", workspace_name):
            continue
        workspace = frappe.get_doc("Workspace", workspace_name)
        rows = _rows(workspace, "links")
        managed_indexes = _regulatory_workspace_managed_indexes(rows)
        custom_links = [
            _workspace_row_values(row) for index, row in enumerate(rows) if index not in managed_indexes
        ]
        managed_card_names = _managed_card_names(rows, managed_indexes)
        custom_content = [
            block
            for block in _content_blocks(workspace)
            if not _is_managed_regulatory_card(block, managed_card_names)
        ]
        custom_tables = {
            fieldname: [_row_values(row) for row in _rows(workspace, fieldname)]
            for fieldname in WORKSPACE_CHILD_TABLE_FIELDS
            if _rows(workspace, fieldname)
        }
        if custom_links or custom_content or custom_tables:
            snapshots[workspace_name] = {
                "links": custom_links,
                "content": custom_content,
                "tables": custom_tables,
            }
    setattr(frappe.flags, REGULATORY_WORKSPACE_MIGRATION_FLAG, snapshots)


def restore_regulatory_workspace_customizations() -> None:
    """Restore workspace rows captured before orphan cleanup."""
    snapshots = getattr(frappe.flags, REGULATORY_WORKSPACE_MIGRATION_FLAG, {})
    if not isinstance(snapshots, dict):
        return
    for source_name, snapshot in snapshots.items():
        target_name = REGULATORY_WORKSPACE if source_name == LEGACY_REGULATORY_WORKSPACE else source_name
        if not isinstance(snapshot, dict) or not frappe.db.exists("Workspace", target_name):
            continue
        workspace = frappe.get_doc("Workspace", target_name)
        current_links = _rows(workspace, "links")
        existing_link_keys = {_workspace_row_key(row) for row in current_links}
        changed = False
        custom_links = snapshot.get("links")
        if isinstance(custom_links, list):
            for row in custom_links:
                if isinstance(row, dict) and _workspace_row_key(row) not in existing_link_keys:
                    workspace.append("links", row)
                    existing_link_keys.add(_workspace_row_key(row))
                    changed = True
        current_content = _content_blocks(workspace)
        custom_content = snapshot.get("content")
        if isinstance(custom_content, list):
            desired_content = [
                *custom_content,
                *[block for block in current_content if block not in custom_content],
            ]
            if desired_content != current_content:
                current_content = desired_content
                changed = True
        custom_tables = snapshot.get("tables")
        if isinstance(custom_tables, dict):
            for fieldname, rows in custom_tables.items():
                if fieldname not in WORKSPACE_CHILD_TABLE_FIELDS or not isinstance(rows, list):
                    continue
                existing_rows = _rows(workspace, fieldname)
                existing_keys = {_row_key(row) for row in existing_rows}
                for row in rows:
                    if isinstance(row, dict) and _row_key(row) not in existing_keys:
                        workspace.append(fieldname, row)
                        existing_keys.add(_row_key(row))
                        changed = True
        if changed:
            _reindex(_rows(workspace, "links"))
            workspace.set("content", json.dumps(current_content, separators=(",", ":")))
            workspace.save(ignore_permissions=True)
    setattr(frappe.flags, REGULATORY_WORKSPACE_MIGRATION_FLAG, {})


def restore_regulatory_sidebar_customizations() -> None:
    """Restore rows captured before standard sidebar files were imported."""
    snapshots = getattr(frappe.flags, REGULATORY_SIDEBAR_MIGRATION_FLAG, {})
    if not isinstance(snapshots, dict):
        return
    for source_name, rows in snapshots.items():
        target_name = REGULATORY_WORKSPACE if source_name == LEGACY_REGULATORY_WORKSPACE else source_name
        if not isinstance(rows, list) or not frappe.db.exists("Workspace Sidebar", target_name):
            continue
        sidebar = frappe.get_doc("Workspace Sidebar", target_name)
        existing_keys = {_sidebar_row_key(row) for row in _rows(sidebar, "items")}
        restored = [row for row in rows if _sidebar_row_key(row) not in existing_keys]
        if not restored:
            continue
        for row in restored:
            sidebar.append("items", row)
        _reindex(_rows(sidebar, "items"))
        _save_sidebar(sidebar)
    setattr(frappe.flags, REGULATORY_SIDEBAR_MIGRATION_FLAG, {})


def _migrate_legacy_regulatory_navigation() -> None:
    """Move the previous public navigation to the new label without leaving duplicates."""
    for doctype in ("Workspace", "Workspace Sidebar"):
        legacy_exists = frappe.db.exists(doctype, LEGACY_REGULATORY_WORKSPACE)
        if not legacy_exists:
            continue

        if not frappe.db.exists(doctype, REGULATORY_WORKSPACE):
            frappe.rename_doc(
                doctype,
                LEGACY_REGULATORY_WORKSPACE,
                REGULATORY_WORKSPACE,
                force=True,
                ignore_permissions=True,
                show_alert=False,
                rebuild_search=False,
            )
            renamed = frappe.get_doc(doctype, REGULATORY_WORKSPACE)
            if doctype == "Workspace":
                renamed.set("label", REGULATORY_WORKSPACE)
                renamed.set("title", REGULATORY_WORKSPACE)
                renamed.set("module", REGULATORY_MODULE)
                renamed.set("icon", REGULATORY_ICON)
            else:
                renamed.set("title", REGULATORY_WORKSPACE)
                renamed.set("module", REGULATORY_MODULE)
                renamed.set("header_icon", REGULATORY_ICON)
            renamed.save(ignore_permissions=True)
            continue

        target = frappe.get_doc(doctype, REGULATORY_WORKSPACE)
        legacy = frappe.get_doc(doctype, LEGACY_REGULATORY_WORKSPACE)
        if doctype == "Workspace":
            _preserve_legacy_workspace_rows(target, legacy)
        else:
            _preserve_legacy_sidebar_rows(target, legacy)
        frappe.delete_doc(
            doctype,
            LEGACY_REGULATORY_WORKSPACE,
            force=True,
            ignore_permissions=True,
        )

    _migrate_legacy_regulatory_personalized_sidebars()
    _migrate_legacy_regulatory_desktop_icons()


def _migrate_legacy_regulatory_personalized_sidebars() -> None:
    """Rename per-user sidebars so saved ordering and links remain reachable."""
    legacy_sidebars = frappe.get_all(
        "Workspace Sidebar",
        filters={
            "for_user": ["is", "set"],
            "title": ["like", f"{LEGACY_REGULATORY_WORKSPACE}-%"],
        },
        pluck="name",
    )
    for old_name in legacy_sidebars:
        suffix = old_name[len(LEGACY_REGULATORY_WORKSPACE) :]
        new_name = f"{REGULATORY_WORKSPACE}{suffix}"
        if old_name == new_name:
            continue
        if not frappe.db.exists("Workspace Sidebar", new_name):
            frappe.rename_doc(
                "Workspace Sidebar",
                old_name,
                new_name,
                force=True,
                ignore_permissions=True,
                show_alert=False,
                rebuild_search=False,
            )
            sidebar = frappe.get_doc("Workspace Sidebar", new_name)
            sidebar.set("title", new_name)
            sidebar.set("module", REGULATORY_MODULE)
            sidebar.set("header_icon", REGULATORY_ICON)
            _retarget_regulatory_sidebar_rows(sidebar)
            sidebar.save(ignore_permissions=True)
            continue

        target = frappe.get_doc("Workspace Sidebar", new_name)
        legacy = frappe.get_doc("Workspace Sidebar", old_name)
        _preserve_legacy_sidebar_rows(target, legacy)
        frappe.delete_doc("Workspace Sidebar", old_name, force=True, ignore_permissions=True)


def _retarget_regulatory_sidebar_rows(sidebar: Document) -> None:
    """Update only the Home link in a personalized sidebar while preserving its order."""
    changed = False
    for row in _rows(sidebar, "items"):
        if row.get("link_type") == "Workspace" and row.get("link_to") == LEGACY_REGULATORY_WORKSPACE:
            row.update({"link_to": REGULATORY_WORKSPACE})
            changed = True
    if changed:
        _reindex(_rows(sidebar, "items"))


def _migrate_legacy_regulatory_desktop_icons() -> None:
    """Retarget user-created desktop icons that still point at the old sidebar."""
    legacy_icons = frappe.get_all(
        "Desktop Icon",
        filters={"link_type": "Workspace Sidebar", "link_to": LEGACY_REGULATORY_WORKSPACE},
        pluck="name",
    )
    for icon_name in legacy_icons:
        if frappe.db.exists("Desktop Icon", REGULATORY_WORKSPACE):
            legacy_icon = frappe.get_doc("Desktop Icon", icon_name)
            if legacy_icon.get("standard") == 0:
                # A user-owned icon must retain its owner-specific layout and
                # visibility.  Only retarget the link; the public standard
                # icon is managed separately.
                legacy_icon.set("link_to", REGULATORY_WORKSPACE)
                legacy_icon.save(ignore_permissions=True)
                continue
            target_icon = frappe.get_doc("Desktop Icon", REGULATORY_WORKSPACE)
            for fieldname in (
                "icon",
                "parent_icon",
                "idx",
                "hidden",
                "roles",
                "bg_color",
                "sidebar",
                "logo_url",
                "restrict_removal",
            ):
                if legacy_icon.get(fieldname) is not None:
                    if fieldname == "roles":
                        target_icon.set(
                            fieldname, [_row_values(row) for row in legacy_icon.get(fieldname) or []]
                        )
                    else:
                        target_icon.set(fieldname, legacy_icon.get(fieldname))
            target_icon.set("icon", target_icon.get("icon") or REGULATORY_ICON)
            target_icon.save(ignore_permissions=True)
            frappe.delete_doc("Desktop Icon", icon_name, force=True, ignore_permissions=True)
            continue
        icon = frappe.get_doc("Desktop Icon", icon_name)
        icon.set("label", REGULATORY_WORKSPACE)
        icon.set("link_to", REGULATORY_WORKSPACE)
        icon.set("icon", REGULATORY_ICON)
        icon.save(ignore_permissions=True)


def _preserve_legacy_workspace_rows(target: Document, legacy: Document) -> None:
    """Keep unmanaged links/content from a legacy workspace before removing it."""
    legacy_rows = _rows(legacy, "links")
    managed_indexes = _regulatory_workspace_managed_indexes(legacy_rows)
    target_rows = _rows(target, "links")
    existing_keys = {_workspace_row_key(row) for row in target_rows}
    custom_links = [
        row
        for index, row in enumerate(legacy_rows)
        if index not in managed_indexes and _workspace_row_key(row) not in existing_keys
    ]
    if custom_links:
        target.set("links", [*custom_links, *_rows(target, "links")])
    managed_card_names = _managed_card_names(legacy_rows, managed_indexes)
    custom_content = [
        block
        for block in _content_blocks(legacy)
        if not _is_managed_regulatory_card(block, managed_card_names)
    ]
    custom_tables = {
        fieldname: [_row_values(row) for row in _rows(legacy, fieldname)]
        for fieldname in WORKSPACE_CHILD_TABLE_FIELDS
        if _rows(legacy, fieldname)
    }
    for fieldname, rows in custom_tables.items():
        existing_table_keys = {_row_key(row) for row in _rows(target, fieldname)}
        for row in rows:
            if _row_key(row) not in existing_table_keys:
                target.append(fieldname, row)
                existing_table_keys.add(_row_key(row))
    if custom_content:
        target.set("content", json.dumps([*custom_content, *_content_blocks(target)], separators=(",", ":")))
    if custom_links or custom_content or custom_tables:
        target.save(ignore_permissions=True)


def _preserve_legacy_sidebar_rows(target: Document, legacy: Document) -> None:
    """Keep unmanaged sidebar items from a legacy sidebar before removing it."""
    legacy_rows = _rows(legacy, "items")
    managed_indexes = _regulatory_sidebar_managed_indexes(legacy_rows)
    target_rows = _rows(target, "items")
    existing_keys = {_sidebar_row_key(row) for row in target_rows}
    custom_rows = [
        row
        for index, row in enumerate(legacy_rows)
        if index not in managed_indexes and _sidebar_row_key(row) not in existing_keys
    ]
    if custom_rows:
        target.set("items", [*custom_rows, *target_rows])
        _reindex(_rows(target, "items"))
        _save_sidebar(target)


def _ensure_regulatory_sidebar(sidebar: Document) -> bool:
    rows = _rows(sidebar, "items")
    expected = _regulatory_sidebar_items()
    managed_indexes = _regulatory_sidebar_managed_indexes(rows)
    section_replacements = _regulatory_sidebar_section_replacements(rows, expected)
    if section_replacements:
        section_indexes = set(section_replacements)
        section_rows: set[int] = set()
        for section_index, (end, _replacement_rows) in section_replacements.items():
            section_rows.update(range(section_index, end))
        custom_rows = [
            row
            for index, row in enumerate(rows)
            if index not in managed_indexes and index not in section_rows
        ]
        desired_rows: list[Document] = [cast(Document, row) for row in custom_rows]
        expected_section_ranges: list[range] = []
        for expected_section_index, expected_section in enumerate(expected):
            if expected_section.get("type") != "Section Break":
                continue
            expected_section_end = next(
                (
                    candidate
                    for candidate in range(expected_section_index + 1, len(expected))
                    if expected[candidate].get("type") == "Section Break"
                    or (expected[candidate].get("type") == "Link" and expected[candidate].get("child") == 0)
                ),
                len(expected),
            )
            expected_section_ranges.append(range(expected_section_index + 1, expected_section_end))
        for expected_index, expected_row in enumerate(expected):
            if expected_row.get("type") == "Section Break":
                matching_index = next(
                    (
                        index
                        for index in section_indexes
                        if rows[index].get("label") == expected_row.get("label")
                    ),
                    None,
                )
                if matching_index is not None:
                    desired_rows.extend(section_replacements[matching_index][1])
                else:
                    desired_rows.append(cast(Document, frappe._dict(expected_row)))
                    expected_section_end = next(
                        (
                            candidate
                            for candidate in range(expected_index + 1, len(expected))
                            if expected[candidate].get("type") == "Section Break"
                        ),
                        len(expected),
                    )
                    desired_rows.extend(
                        cast(Document, frappe._dict(child))
                        for child in expected[expected_index + 1 : expected_section_end]
                    )
                continue
            if not any(expected_index in section_range for section_range in expected_section_ranges):
                desired_rows.append(cast(Document, frappe._dict(expected_row)))
        if [_sidebar_row_values(row) for row in rows] != [_sidebar_row_values(row) for row in desired_rows]:
            sidebar.set("items", desired_rows)
            _reindex(_rows(sidebar, "items"))
            return True
        return False
    retained_rows = [row for index, row in enumerate(rows) if index not in managed_indexes]
    managed_rows = [rows[index] for index in sorted(managed_indexes)]
    if (
        len(rows) == len(retained_rows) + len(expected)
        and rows[: len(retained_rows)] == retained_rows
        and all(_sidebar_row_matches(row, values) for row, values in zip(managed_rows, expected, strict=True))
    ):
        return False
    sidebar.set("items", retained_rows)
    for values in expected:
        sidebar.append("items", values)
    _reindex(_rows(sidebar, "items"))
    return True


def _ensure_regulatory_workspace_cards(workspace: Document) -> bool:
    expected_rows: list[dict[str, str | int]] = []
    for group in REGULATORY_WORKSPACE_GROUPS:
        expected_rows.append({"type": "Card Break", "label": group.name, "link_count": 0})
        expected_rows.extend(_workspace_link_values(link) for link in group.links)

    rows = _rows(workspace, "links")
    managed_indexes = _regulatory_workspace_managed_indexes(rows)
    retained_rows = [row for index, row in enumerate(rows) if index not in managed_indexes]
    managed_rows = [rows[index] for index in sorted(managed_indexes)]
    if (
        len(rows) == len(retained_rows) + len(expected_rows)
        and rows[: len(retained_rows)] == retained_rows
        and all(
            _workspace_row_matches(row, values)
            for row, values in zip(managed_rows, expected_rows, strict=True)
        )
    ):
        rows_changed = False
    else:
        workspace.set("links", retained_rows)
        for values in expected_rows:
            workspace.append("links", values)
        _reindex(_rows(workspace, "links"))
        rows_changed = True

    content = _content_blocks(workspace)
    managed_card_names = _managed_card_names(rows, managed_indexes)
    retained_content = [
        block for block in content if not _is_managed_regulatory_card(block, managed_card_names)
    ]
    card_blocks = [
        {
            "type": "card",
            "data": {"card_name": group.name, "col": 4, "managed_by": "connect_diagnostics_core"},
        }
        for group in REGULATORY_WORKSPACE_GROUPS
    ]
    desired_content = [*retained_content, *card_blocks]
    content_changed = desired_content != content
    if content_changed:
        workspace.set("content", json.dumps(desired_content, separators=(",", ":")))
    return rows_changed or content_changed


def _regulatory_sidebar_managed_indexes(rows: list[Document]) -> set[int]:
    """Identify canonical sidebar rows without consuming same-named custom sections."""
    expected = _regulatory_sidebar_items()
    managed_indexes = {
        index
        for index, row in enumerate(rows)
        if row.get("type") == "Link"
        and (
            (
                row.get("link_type") == "Workspace"
                and row.get("link_to")
                in {
                    REGULATORY_WORKSPACE,
                    LEGACY_REGULATORY_WORKSPACE,
                }
            )
            or any(
                row.get("link_type") == link.link_type and row.get("link_to") == link.link_to
                for link in REGULATORY_LINKS
            )
        )
    }
    for index, row in enumerate(rows):
        if row.get("type") == "Section Break" and row.get("label") in {
            NAVIGATION_LABEL,
            LEGACY_REGULATORY_WORKSPACE,
        }:
            managed_indexes.add(index)
    for index, (end, _replacement_rows) in _regulatory_sidebar_section_replacements(rows, expected).items():
        managed_indexes.add(index)
        section_label = rows[index].get("label")
        expected_index = next(
            expected_index
            for expected_index, expected_row in enumerate(expected)
            if expected_row.get("type") == "Section Break" and expected_row.get("label") == section_label
        )
        expected_children = expected[expected_index + 1 :]
        expected_children = expected_children[:5] if section_label == "Reports" else expected_children[:1]
        for child_index in range(index + 1, end):
            if any(_sidebar_row_matches(rows[child_index], child) for child in expected_children):
                managed_indexes.add(child_index)
    return managed_indexes


def _regulatory_sidebar_section_replacements(
    rows: list[Document], expected: list[dict[str, str | int]]
) -> dict[int, tuple[int, list[Document]]]:
    """Find Reports/Setup sections while retaining custom children in place."""
    replacements: dict[int, tuple[int, list[Document]]] = {}
    expected_sections = {
        row.get("label"): index
        for index, row in enumerate(expected)
        if row.get("type") == "Section Break" and row.get("label") in {"Reports", "Setup"}
    }
    for index, row in enumerate(rows):
        label = row.get("label")
        expected_index = expected_sections.get(label)
        if row.get("type") != "Section Break" or expected_index is None:
            continue
        end = next(
            (
                candidate
                for candidate in range(index + 1, len(rows))
                if rows[candidate].get("type") == "Section Break"
                or (rows[candidate].get("type") == "Link" and rows[candidate].get("child") == 0)
            ),
            len(rows),
        )
        expected_children = expected[expected_index + 1 :]
        expected_children = expected_children[:5] if label == "Reports" else expected_children[:1]
        matched_indexes: set[int] = set()
        for expected_child in expected_children:
            match = next(
                (
                    candidate
                    for candidate in range(index + 1, end)
                    if candidate not in matched_indexes
                    and _sidebar_row_matches(rows[candidate], expected_child)
                ),
                None,
            )
            if match is None:
                break
            matched_indexes.add(match)
        else:
            custom_children = [
                rows[candidate] for candidate in range(index + 1, end) if candidate not in matched_indexes
            ]
            replacements[index] = (
                end,
                [
                    cast(Document, frappe._dict(expected[expected_index])),
                    *[cast(Document, frappe._dict(child)) for child in expected_children],
                    *[cast(Document, child) for child in custom_children],
                ],
            )
    return replacements


def _regulatory_workspace_managed_indexes(rows: list[Document]) -> set[int]:
    """Identify only the canonical Regulatory card/link blocks, not same-named custom cards."""
    managed_indexes: set[int] = set()
    for index, row in enumerate(rows):
        if row.get("type") == "Card Break" and row.get("label") in {
            NAVIGATION_LABEL,
            LEGACY_REGULATORY_WORKSPACE,
        }:
            managed_indexes.add(index)
            continue
        for group in REGULATORY_WORKSPACE_GROUPS:
            if row.get("type") != "Card Break" or row.get("label") != group.name:
                continue
            expected_links = group.links
            block = rows[index + 1 : index + 1 + len(expected_links)]
            if len(block) == len(expected_links) and all(
                _workspace_row_matches(link_row, _workspace_link_values(link))
                for link_row, link in zip(block, expected_links, strict=True)
            ):
                managed_indexes.update(range(index, index + 1 + len(expected_links)))
            break
    managed_indexes.update(
        index
        for index, row in enumerate(rows)
        if row.get("type") == "Link"
        and any(
            row.get("link_type") == link.link_type and row.get("link_to") == link.link_to
            for link in REGULATORY_LINKS
        )
    )
    return managed_indexes


def _workspace_row_values(row: Document) -> dict[str, object]:
    return {
        fieldname: row.get(fieldname) for fieldname in WORKSPACE_LINK_FIELDS if row.get(fieldname) is not None
    }


def _workspace_row_key(row: Document | dict[str, object]) -> tuple[object, ...]:
    return tuple(row.get(fieldname) for fieldname in WORKSPACE_LINK_KEY_FIELDS)


def _row_values(row: Document | Mapping[str, object]) -> dict[str, object]:
    values = row.as_dict() if isinstance(row, Document) else dict(row)
    return {
        key: value
        for key, value in values.items()
        if key
        not in {
            "name",
            "owner",
            "creation",
            "modified",
            "modified_by",
            "docstatus",
            "idx",
            "parent",
            "parentfield",
            "parenttype",
        }
    }


def _row_key(row: Document | Mapping[str, object]) -> str:
    return json.dumps(_row_values(row), sort_keys=True, default=str, separators=(",", ":"))


def _regulatory_sidebar_items() -> list[dict[str, str | int]]:
    items: list[dict[str, str | int]] = [
        {
            "type": "Link",
            "label": "Home",
            "link_type": "Workspace",
            "link_to": REGULATORY_WORKSPACE,
            "child": 0,
            "collapsible": 1,
            "icon": "home",
            "indent": 0,
            "keep_closed": 0,
            "show_arrow": 0,
        },
    ]
    main_group, *section_groups = REGULATORY_WORKSPACE_GROUPS
    settings_group = section_groups.pop()
    items.extend(
        _regulatory_sidebar_link_values(link, child=0, icon=_regulatory_link_icon(link))
        for link in main_group.links
    )
    for group in section_groups:
        items.append(_regulatory_sidebar_section_values(group.name))
        items.extend(_regulatory_sidebar_link_values(link, child=1, icon="") for link in group.links)
    items.extend(
        _regulatory_sidebar_link_values(link, child=0, icon="settings") for link in settings_group.links
    )
    return items


def _sidebar_row_values(row: Document | Mapping[str, object]) -> dict[str, object]:
    return {
        fieldname: row.get(fieldname) for fieldname in SIDEBAR_ITEM_FIELDS if row.get(fieldname) is not None
    }


def _sidebar_row_key(row: Document | dict[str, object]) -> tuple[object, ...]:
    return tuple(row.get(fieldname) for fieldname in SIDEBAR_ITEM_FIELDS)


def _regulatory_sidebar_section_values(label: str) -> dict[str, str | int]:
    icons = {"Reports": "sheet", "Setup": "database"}
    return {
        "type": "Section Break",
        "label": label,
        "link_type": "DocType",
        "child": 0,
        "collapsible": 1,
        "icon": icons[label],
        "indent": 1,
        "keep_closed": 1,
        "show_arrow": 0,
    }


def _regulatory_sidebar_link_values(link: NavigationLink, *, child: int, icon: str) -> dict[str, str | int]:
    return {
        "type": "Link",
        "label": link.label,
        "link_type": link.link_type,
        "link_to": link.link_to,
        "child": child,
        "collapsible": 1,
        "icon": icon,
        "indent": 0,
        "keep_closed": 0,
        "show_arrow": 0,
    }


def _regulatory_link_icon(link: NavigationLink) -> str:
    return {
        "Medical Device Product Registration": "file-text",
        "Medical Device Regulatory Document": "file",
        "Medical Device Registration Action": "git-pull-request-arrow",
        "Medical Device Regulatory Override": "shield-alert",
    }.get(link.link_to, "")


def _workspace_row_matches(row: Document, expected: dict[str, str | int]) -> bool:
    return all(row.get(fieldname) == value for fieldname, value in expected.items())


def _sidebar_row_matches(row: Document, expected: dict[str, str | int]) -> bool:
    return all(row.get(fieldname) == value for fieldname, value in expected.items())


def _is_regulatory_workspace_row(row: Document) -> bool:
    if row.get("type") == "Card Break":
        return row.get("label") in {
            NAVIGATION_LABEL,
            LEGACY_REGULATORY_WORKSPACE,
            *(group.name for group in REGULATORY_WORKSPACE_GROUPS),
        }
    return row.get("type") == "Link" and any(
        row.get("link_type") == link.link_type and row.get("link_to") == link.link_to
        for link in REGULATORY_LINKS
    )


def _is_regulatory_sidebar_row(row: Document) -> bool:
    if row.get("type") == "Section Break":
        return row.get("label") in {
            NAVIGATION_LABEL,
            LEGACY_REGULATORY_WORKSPACE,
            *(group.name for group in REGULATORY_WORKSPACE_GROUPS),
        }
    if row.get("type") != "Link":
        return False
    if row.get("link_type") == "Workspace" and row.get("link_to") in {
        REGULATORY_WORKSPACE,
        LEGACY_REGULATORY_WORKSPACE,
    }:
        return True
    return any(
        row.get("link_type") == link.link_type and row.get("link_to") == link.link_to
        for link in REGULATORY_LINKS
    )


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

    if not group.links:
        if card_break is not None:
            rows.remove(card_break)
            _reindex(rows)
            changed = True
        if _remove_card_block(workspace):
            changed = True
        return changed

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


def _remove_card_block(workspace: Document) -> bool:
    content = _content_blocks(workspace)
    remaining = [block for block in content if not _is_card_block(block)]
    if len(remaining) == len(content):
        return False
    workspace.set("content", json.dumps(remaining, separators=(",", ":")))
    return True


def _is_card_block(block: dict[str, object]) -> bool:
    return _is_named_card(block, NAVIGATION_LABEL)


def _is_named_card(block: dict[str, object], card_name: str) -> bool:
    data = block.get("data")
    if not isinstance(data, dict):
        return False
    card_data = cast(dict[str, object], data)
    return block.get("type") == "card" and card_data.get("card_name") == card_name


def _managed_card_names(rows: list[Document], managed_indexes: set[int]) -> set[str]:
    return {
        NAVIGATION_LABEL,
        LEGACY_REGULATORY_WORKSPACE,
        *(
            str(row.get("label"))
            for index, row in enumerate(rows)
            if index in managed_indexes and row.get("type") == "Card Break" and row.get("label")
        ),
    }


def _is_managed_regulatory_card(block: dict[str, object], card_names: set[str] | None = None) -> bool:
    """Identify canonical regulatory cards without consuming same-named custom cards."""
    data = block.get("data")
    if not isinstance(data, dict) or block.get("type") != "card":
        return False
    card_data = cast(dict[str, object], data)
    card_name = card_data.get("card_name")
    managed_names = card_names or {NAVIGATION_LABEL, LEGACY_REGULATORY_WORKSPACE}
    if card_name not in managed_names:
        return False
    if card_data.get("managed_by") == "connect_diagnostics_core":
        return True
    if card_name not in {NAVIGATION_LABEL, LEGACY_REGULATORY_WORKSPACE}:
        return False
    return block == {"type": "card", "data": {"card_name": card_name, "col": 4}}


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


def _remove_retired_card_links(workspace: Document, workspace_name: str) -> bool:
    retired_links = RETIRED_CARD_LINKS.get(workspace_name, frozenset())
    if not retired_links:
        return False
    rows = _rows(workspace, "links")
    retained_rows = [
        row
        for row in rows
        if (str(row.get("link_type") or ""), str(row.get("link_to") or "")) not in retired_links
    ]
    if len(retained_rows) == len(rows):
        return False
    rows[:] = retained_rows
    _reindex(rows)
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
