# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Any, cast
from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.tests import UnitTestCase

from connect_diagnostics_core.setup import workspace


class FakeDocument(frappe._dict):
    """In-memory document double that preserves child-table rows."""

    save_count: int

    def __init__(self, **values: Any) -> None:
        super().__init__(values)
        self.save_count = 0

    def append(self, fieldname: str, values: dict[str, Any]) -> None:
        self.setdefault(fieldname, []).append(frappe._dict(values))

    def set(self, key: str, value: Any) -> None:
        self[key] = value

    def save(self, **_: Any) -> None:
        self.save_count += 1


def workspace_documents() -> dict[str, FakeDocument]:
    return {
        group.name: FakeDocument(name=group.name, parent_page="", links=[], content="[]")
        for group in workspace.NAVIGATION_GROUPS
    }


def sidebar_documents() -> dict[str, FakeDocument]:
    return {
        "Financial Reports": FakeDocument(
            name="Financial Reports",
            items=[
                sidebar_section("Financial Reports"),
                sidebar_link("Trial Balance", child=1),
                sidebar_section("Ledgers"),
                sidebar_link("General Ledger", child=1),
            ],
        ),
        "Invoicing": FakeDocument(name="Invoicing", items=[sidebar_link("Account")]),
        "Selling": FakeDocument(
            name="Selling",
            items=[
                sidebar_link("Sales Order"),
                sidebar_link("Sales Invoice"),
                sidebar_section("Setup"),
                sidebar_link("Customer", child=1),
                sidebar_link("Sales Taxes and Charges Template", child=1),
                sidebar_section("Reports"),
                sidebar_link("Sales Register", child=1),
            ],
        ),
        "Stock": FakeDocument(
            name="Stock",
            items=[
                sidebar_link("Pick List"),
                sidebar_section("Setup"),
                sidebar_link("Item", child=1),
            ],
        ),
        "Buying": FakeDocument(name="Buying", items=[sidebar_link("Purchase Invoice")]),
        "ERPNext Settings": FakeDocument(
            name="ERPNext Settings",
            items=[
                sidebar_section("Other Settings"),
                sidebar_link("Subscription Settings", child=1),
            ],
        ),
    }


def sidebar_link(link_to: str, *, child: int = 0) -> frappe._dict:
    return frappe._dict(
        {
            "type": "Link",
            "label": link_to,
            "link_type": "DocType",
            "link_to": link_to,
            "child": child,
        }
    )


def sidebar_section(label: str) -> frappe._dict:
    return frappe._dict({"type": "Section Break", "label": label, "child": 0})


def get_document(
    workspaces: dict[str, FakeDocument], sidebars: dict[str, FakeDocument], doctype: str, name: str
) -> FakeDocument:
    return workspaces[name] if doctype == "Workspace" else sidebars[name]


class TestWorkspaceNavigation(UnitTestCase):
    def test_every_module_receives_a_workspace_card_and_contextual_sidebar_links(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()

        with patch.object(
            workspace.frappe,
            "get_doc",
            side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
        ):
            workspace.ensure_workspace_navigation()

        for group in workspace.NAVIGATION_GROUPS:
            with self.subTest(module=group.name):
                workspace_doc = workspaces[group.name]
                sidebar_doc = sidebars[group.name]
                self.assertEqual(workspace_doc.save_count, 1)
                self.assertEqual(sidebar_doc.save_count, 1)
                self.assertEqual(
                    [row["link_to"] for row in workspace_doc["links"] if row.get("type") == "Link"],
                    [link.link_to for link in group.links],
                )
                self.assertEqual(workspace_doc["links"][0]["label"], workspace.NAVIGATION_LABEL)
                self.assertEqual(
                    [block["data"]["card_name"] for block in json.loads(workspace_doc["content"])],
                    [workspace.NAVIGATION_LABEL],
                )
                self.assertNotIn(
                    workspace.NAVIGATION_LABEL,
                    [row.get("label") for row in sidebar_doc["items"] if row.get("type") == "Section Break"],
                )
                for link in group.links:
                    self.assertEqual(
                        sum(row.get("link_to") == link.link_to for row in sidebar_doc["items"]),
                        1,
                    )

    def test_reports_include_workspace_routing_metadata(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()

        with patch.object(
            workspace.frappe,
            "get_doc",
            side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
        ):
            workspace.ensure_workspace_navigation()

        reports = [
            row
            for document in workspaces.values()
            for row in document["links"]
            if row.get("link_type") == "Report"
        ]
        self.assertEqual(
            {(row["link_to"], row["report_ref_doctype"], row["is_query_report"]) for row in reports},
            {
                ("General Ledger TH", "GL Entry", 1),
                ("Trial Balance TH", "GL Entry", 1),
                ("Trial Balance TH Detail", "GL Entry", 1),
                ("Back Orders", "Sales Order", 1),
            },
        )
        self.assertEqual(sum(row["link_to"] == "Back Orders" for row in reports), 2)

    def test_sync_is_idempotent_and_preserves_existing_navigation(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()
        workspaces["Selling"] = FakeDocument(
            name="Selling",
            parent_page="",
            links=[
                frappe._dict({"type": "Card Break", "label": "Existing Card"}),
                frappe._dict(
                    {"type": "Link", "label": "Customer", "link_type": "DocType", "link_to": "Customer"}
                ),
            ],
            content='[{"type":"card","data":{"card_name":"Existing Card","col":4}}]',
        )
        sidebars["Selling"]["items"].insert(0, sidebar_link("Home"))

        with patch.object(
            workspace.frappe,
            "get_doc",
            side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
        ):
            workspace.ensure_workspace_navigation()
            workspace.ensure_workspace_navigation()

        selling_workspace = workspaces["Selling"]
        selling_sidebar = sidebars["Selling"]
        self.assertEqual(selling_workspace.save_count, 1)
        self.assertEqual(selling_sidebar.save_count, 1)
        self.assertEqual(selling_workspace["links"][0]["label"], "Existing Card")
        self.assertEqual(selling_workspace["links"][1]["link_to"], "Customer")
        self.assertNotIn(
            workspace.NAVIGATION_LABEL,
            [row.get("label") for row in selling_sidebar["items"] if row.get("type") == "Section Break"],
        )
        self.assertEqual(sum(row.get("link_to") == "Home" for row in selling_sidebar["items"]), 1)
        self.assertEqual(sum(row.get("link_to") == "Customer" for row in selling_sidebar["items"]), 1)

    def test_stale_missing_workspace_parent_is_cleared_before_save(self) -> None:
        financial_reports = FakeDocument(
            name="Financial Reports",
            parent_page="Accounting",
            links=[],
            content="[]",
        )

        with patch.object(workspace.frappe.db, "exists", return_value=False):
            changed = workspace._repair_stale_parent_page(cast(Document, financial_reports))

        self.assertTrue(changed)
        self.assertEqual(financial_reports["parent_page"], "")

    def test_existing_parent_is_not_cleared(self) -> None:
        financial_reports = FakeDocument(
            name="Financial Reports",
            parent_page="Accounting",
            links=[],
            content="[]",
        )

        with patch.object(workspace.frappe.db, "exists", return_value=True):
            changed = workspace._repair_stale_parent_page(cast(Document, financial_reports))

        self.assertFalse(changed)
        self.assertEqual(financial_reports["parent_page"], "Accounting")

    def test_obsolete_repost_settings_link_is_removed_from_erpnext_settings(self) -> None:
        sidebar = FakeDocument(
            name="ERPNext Settings",
            items=[
                frappe._dict(
                    {"type": "Link", "link_type": "DocType", "link_to": "Repost Accounting Ledger Settings"}
                ),
                frappe._dict({"type": "Link", "link_type": "DocType", "link_to": "Accounts Settings"}),
            ],
        )

        changed = workspace._remove_retired_sidebar_links(cast(Document, sidebar), "ERPNext Settings")

        self.assertTrue(changed)
        self.assertEqual([row["link_to"] for row in sidebar["items"]], ["Accounts Settings"])

    def test_stock_links_are_distributed_between_primary_navigation_and_setup(self) -> None:
        sidebar = FakeDocument(
            name="Stock",
            items=[
                sidebar_section(workspace.NAVIGATION_LABEL),
                sidebar_link("DKSH Item", child=1),
                sidebar_link("Product Group", child=1),
                sidebar_link("Regulation Class", child=1),
                sidebar_link("Storage Condition", child=1),
                sidebar_link("Back Orders", child=1),
                sidebar_link("Pick List"),
                sidebar_section("Setup"),
                sidebar_link("Item", child=1),
            ],
        )
        group = next(group for group in workspace.NAVIGATION_GROUPS if group.name == "Stock")

        changed = workspace._ensure_sidebar_navigation(cast(Document, sidebar), group)

        self.assertTrue(changed)
        self.assertNotIn(
            workspace.NAVIGATION_LABEL,
            [row.get("label") for row in sidebar["items"] if row.get("type") == "Section Break"],
        )
        pick_list_index = next(
            index for index, row in enumerate(sidebar["items"]) if row.get("link_to") == "Pick List"
        )
        self.assertEqual(sidebar["items"][pick_list_index + 1]["link_to"], "Back Orders")
        self.assertEqual(sidebar["items"][pick_list_index + 1]["child"], 0)
        item_index = next(index for index, row in enumerate(sidebar["items"]) if row.get("link_to") == "Item")
        self.assertEqual(
            [row["link_to"] for row in sidebar["items"][item_index + 1 : item_index + 5]],
            ["DKSH Item", "Product Group", "Regulation Class", "Storage Condition"],
        )
        self.assertTrue(all(row["child"] == 1 for row in sidebar["items"][item_index + 1 : item_index + 5]))

    def test_existing_workspace_card_links_are_reordered_by_priority(self) -> None:
        workspace_doc = FakeDocument(
            name="Financial Reports",
            parent_page="",
            links=[
                frappe._dict({"type": "Card Break", "label": workspace.NAVIGATION_LABEL}),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "Trial Balance TH Detail",
                        "link_type": "Report",
                        "link_to": "Trial Balance TH Detail",
                    }
                ),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "General Ledger TH",
                        "link_type": "Report",
                        "link_to": "General Ledger TH",
                    }
                ),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "Trial Balance TH",
                        "link_type": "Report",
                        "link_to": "Trial Balance TH",
                    }
                ),
            ],
            content='[{"type":"card","data":{"card_name":"Connect Diagnostics","col":4}}]',
        )
        group = next(group for group in workspace.NAVIGATION_GROUPS if group.name == "Financial Reports")

        changed = workspace._ensure_workspace_card(cast(Document, workspace_doc), group)

        self.assertTrue(changed)
        self.assertEqual(
            [row.get("link_to") for row in workspace_doc["links"][1:]],
            [link.link_to for link in group.links],
        )
