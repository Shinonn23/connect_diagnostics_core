# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from pathlib import Path
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

    def is_new(self) -> bool:
        return False


def workspace_documents() -> dict[str, FakeDocument]:
    documents = {
        group.name: FakeDocument(name=group.name, parent_page="", links=[], content="[]")
        for group in workspace.NAVIGATION_GROUPS
    }
    documents[workspace.REGULATORY_WORKSPACE] = FakeDocument(
        name=workspace.REGULATORY_WORKSPACE,
        parent_page="",
        links=[],
        content="[]",
    )
    documents[workspace.STOCK_COUNT_WORKSPACE] = FakeDocument(
        name=workspace.STOCK_COUNT_WORKSPACE,
        parent_page="",
        links=[],
        content="[]",
    )
    return documents


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
        "Taxes": FakeDocument(
            name="Taxes",
            items=[
                sidebar_link("Tax Withholding Category"),
                sidebar_link("Tax Withholding Group"),
                sidebar_link("TDS Computation Summary", link_type="Report"),
                sidebar_link("Tax Category"),
            ],
        ),
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
        "HR Setup": FakeDocument(
            name="HR Setup",
            items=[
                sidebar_link("Employee"),
                sidebar_section("Setup"),
                sidebar_link("Department", child=1),
            ],
        ),
        "Payroll": FakeDocument(
            name="Payroll",
            items=[
                sidebar_link("Payroll Entry"),
                sidebar_section("Setup"),
                sidebar_link("Salary Structure", child=1),
            ],
        ),
        workspace.REGULATORY_WORKSPACE: FakeDocument(name=workspace.REGULATORY_WORKSPACE, items=[]),
        workspace.STOCK_COUNT_WORKSPACE: FakeDocument(name=workspace.STOCK_COUNT_WORKSPACE, items=[]),
    }


def sidebar_link(link_to: str, *, child: int = 0, link_type: str = "DocType") -> frappe._dict:
    return frappe._dict(
        {
            "type": "Link",
            "label": link_to,
            "link_type": link_type,
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


def existing_document(doctype: str, name: str) -> bool:
    """Model the test fixture's current documents without a legacy navigation record.

    The fixture holds no Desktop Icons, so ``ensure_desktop_icons`` is a no-op inside
    the Workspace/Workspace Sidebar flows; it is covered by its own tests below.
    """
    if doctype == "Desktop Icon":
        return False
    return not (
        doctype in {"Workspace", "Workspace Sidebar"} and name == workspace.LEGACY_REGULATORY_WORKSPACE
    )


class TestWorkspaceNavigation(UnitTestCase):
    def test_every_module_receives_a_workspace_card_and_contextual_sidebar_links(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
        ):
            workspace.ensure_workspace_navigation()
            workspace.ensure_workspace_navigation()

        for group in workspace.NAVIGATION_GROUPS:
            with self.subTest(module=group.name):
                workspace_doc = workspaces[group.name]
                sidebar_doc = sidebars[group.name]
                if not group.links:
                    # A group with no managed links (e.g. a retired report group)
                    # has nothing to sync onto an already-empty fixture.
                    self.assertEqual(workspace_doc.save_count, 0)
                    self.assertEqual(sidebar_doc.save_count, 0)
                    self.assertEqual(workspace_doc["links"], [])
                    continue
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

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
        ):
            workspace.ensure_workspace_navigation()

        reports = [
            row
            for group in workspace.NAVIGATION_GROUPS
            for row in workspaces[group.name]["links"]
            if row.get("link_type") == "Report"
        ]
        self.assertEqual(
            {(row["link_to"], row["report_ref_doctype"], row["is_query_report"]) for row in reports},
            {
                ("Back Orders", "Sales Order", 1),
                ("Short Expiry Report", "Item", 1),
                ("Goods Receipt Report", "Purchase Receipt", 1),
            },
        )
        self.assertEqual(sum(row["link_to"] == "Back Orders" for row in reports), 2)
        self.assertEqual(sum(row["link_to"] == "Short Expiry Report" for row in reports), 1)
        self.assertEqual(sum(row["link_to"] == "Goods Receipt Report" for row in reports), 1)

    def test_tds_links_are_removed_from_the_taxes_sidebar(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
        ):
            workspace.ensure_workspace_navigation()

        self.assertEqual(
            [row["link_to"] for row in sidebars["Taxes"]["items"]],
            ["Tax Category"],
        )

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

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
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

    def test_regulatory_workspace_and_sidebar_are_idempotent(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
        ):
            workspace.ensure_workspace_navigation()
            workspace.ensure_workspace_navigation()

        regulatory_workspace = workspaces[workspace.REGULATORY_WORKSPACE]
        regulatory_sidebar = sidebars[workspace.REGULATORY_WORKSPACE]
        expected_links = [link.link_to for link in workspace.REGULATORY_LINKS]
        expected_groups = [group.name for group in workspace.REGULATORY_WORKSPACE_GROUPS]
        self.assertEqual(regulatory_workspace.save_count, 1)
        self.assertEqual(regulatory_sidebar.save_count, 1)
        self.assertEqual(regulatory_workspace["icon"], workspace.REGULATORY_ICON)
        self.assertEqual(
            [row["label"] for row in regulatory_workspace["links"] if row.get("type") == "Card Break"],
            expected_groups,
        )
        self.assertEqual(
            [row["link_to"] for row in regulatory_workspace["links"] if row.get("type") == "Link"],
            expected_links,
        )
        self.assertEqual(
            [block["data"]["card_name"] for block in json.loads(regulatory_workspace["content"])],
            expected_groups,
        )
        self.assertEqual(regulatory_sidebar["header_icon"], workspace.REGULATORY_ICON)
        regulatory_sidebar_items = regulatory_sidebar["items"]
        self.assertEqual(regulatory_sidebar_items[0]["label"], "Home")
        self.assertEqual(regulatory_sidebar_items[0]["link_type"], "Workspace")
        self.assertEqual(
            [row["label"] for row in regulatory_sidebar_items if row.get("type") == "Section Break"],
            expected_groups[1:-1],
        )
        self.assertEqual(
            [row["link_to"] for row in regulatory_sidebar_items if row.get("type") == "Link"],
            [workspace.REGULATORY_WORKSPACE, *expected_links],
        )
        settings_item = regulatory_sidebar_items[-1]
        self.assertEqual(settings_item["link_to"], "Medical Device Regulatory Settings")
        self.assertEqual(settings_item["child"], 0)
        self.assertEqual(settings_item["icon"], "settings")

    def test_stock_count_workspace_and_sidebar_are_idempotent(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
        ):
            workspace.ensure_stock_count_workspace()
            workspace.ensure_stock_count_workspace()

        stock_count_workspace = workspaces[workspace.STOCK_COUNT_WORKSPACE]
        stock_count_sidebar = sidebars[workspace.STOCK_COUNT_WORKSPACE]
        expected_groups = [group.name for group in workspace.STOCK_COUNT_WORKSPACE_GROUPS]

        self.assertEqual(stock_count_workspace.save_count, 1)
        self.assertEqual(stock_count_sidebar.save_count, 1)
        self.assertEqual(stock_count_workspace["icon"], workspace.STOCK_COUNT_ICON)
        self.assertEqual(
            [row["label"] for row in stock_count_workspace["links"] if row.get("type") == "Card Break"],
            expected_groups,
        )
        self.assertEqual(
            [row["link_to"] for row in stock_count_workspace["links"] if row.get("type") == "Link"],
            ["Stock Count", "Stock Count Variance"],
        )
        self.assertEqual(
            [block["data"]["card_name"] for block in json.loads(stock_count_workspace["content"])],
            expected_groups,
        )
        self.assertEqual(stock_count_sidebar["header_icon"], workspace.STOCK_COUNT_ICON)
        sidebar_items = stock_count_sidebar["items"]
        self.assertEqual(sidebar_items[0]["label"], "Home")
        self.assertEqual(sidebar_items[0]["link_type"], "Workspace")
        self.assertEqual(
            [row["link_to"] for row in sidebar_items if row.get("type") == "Link"],
            [workspace.STOCK_COUNT_WORKSPACE, "Stock Count", "Stock Count Variance"],
        )
        self.assertEqual(
            [row["label"] for row in sidebar_items if row.get("type") == "Section Break"],
            ["Reports"],
        )
        variance_item = sidebar_items[-1]
        self.assertEqual(variance_item["link_to"], "Stock Count Variance")
        self.assertEqual(variance_item["child"], 1)
        self.assertEqual(variance_item["is_query_report"], 1)
        self.assertEqual(variance_item["report_ref_doctype"], "Stock Count")

    def test_inventory_desktop_icon_folder_groups_the_stock_workspaces(self) -> None:
        desktop_icon_dir = Path(__file__).parents[2] / "desktop_icon"
        inventory = json.loads((desktop_icon_dir / "inventory.json").read_text())
        stock_counting = json.loads((desktop_icon_dir / "stock_counting.json").read_text())

        self.assertEqual(inventory["doctype"], "Desktop Icon")
        self.assertEqual(inventory["name"], workspace.INVENTORY_DESKTOP_ICON)
        self.assertEqual(inventory["label"], workspace.INVENTORY_DESKTOP_ICON)
        self.assertEqual(inventory["icon_type"], "Folder")
        self.assertEqual(inventory["link_to"], "")
        self.assertEqual(inventory["parent_icon"], "")
        self.assertEqual(inventory["app"], "connect_diagnostics_core")
        self.assertEqual(inventory["standard"], 1)
        self.assertEqual(inventory["hidden"], 0)
        self.assertTrue(inventory["modified"])

        self.assertEqual(stock_counting["doctype"], "Desktop Icon")
        self.assertEqual(stock_counting["name"], workspace.STOCK_COUNT_WORKSPACE)
        self.assertEqual(stock_counting["label"], workspace.STOCK_COUNT_WORKSPACE)
        self.assertEqual(stock_counting["icon_type"], "Link")
        self.assertEqual(stock_counting["link_type"], "Workspace Sidebar")
        self.assertEqual(stock_counting["link_to"], workspace.STOCK_COUNT_WORKSPACE)
        self.assertEqual(stock_counting["parent_icon"], workspace.INVENTORY_DESKTOP_ICON)
        self.assertEqual(stock_counting["icon"], workspace.STOCK_COUNT_ICON)
        self.assertEqual(stock_counting["app"], "connect_diagnostics_core")
        self.assertEqual(stock_counting["standard"], 1)
        self.assertEqual(stock_counting["hidden"], 0)
        self.assertTrue(stock_counting["modified"])
        # ERPNext ships the Stock icon at idx 1, so Stock Counting must sort after it.
        self.assertGreater(stock_counting["idx"], 1)

        for variant in ("subtle", "solid"):
            self.assertTrue(
                (
                    Path(__file__).parents[2]
                    / "public"
                    / "icons"
                    / "desktop_icons"
                    / variant
                    / "stock_counting.svg"
                ).is_file()
            )

    def test_stock_desktop_icon_is_reparented_under_inventory(self) -> None:
        stock_icon = FakeDocument(
            name=workspace.STOCK_DESKTOP_ICON, parent_icon=workspace.ERPNEXT_DESKTOP_ICON
        )

        with (
            patch.object(workspace.frappe.db, "exists", return_value=True),
            patch.object(workspace.frappe.db, "get_value", side_effect=lambda *_: stock_icon["parent_icon"]),
            patch.object(workspace.frappe, "get_doc", return_value=stock_icon),
        ):
            workspace.ensure_desktop_icons()
            workspace.ensure_desktop_icons()

        self.assertEqual(stock_icon["parent_icon"], workspace.INVENTORY_DESKTOP_ICON)
        self.assertEqual(stock_icon.save_count, 1)

    def test_stock_desktop_icon_falls_back_to_erpnext_when_inventory_is_missing(self) -> None:
        stock_icon = FakeDocument(
            name=workspace.STOCK_DESKTOP_ICON, parent_icon=workspace.INVENTORY_DESKTOP_ICON
        )
        present = {workspace.STOCK_DESKTOP_ICON, workspace.ERPNEXT_DESKTOP_ICON}

        with (
            patch.object(workspace.frappe.db, "exists", side_effect=lambda _doctype, name: name in present),
            patch.object(workspace.frappe.db, "get_value", side_effect=lambda *_: stock_icon["parent_icon"]),
            patch.object(workspace.frappe, "get_doc", return_value=stock_icon),
        ):
            workspace.ensure_desktop_icons()

        self.assertEqual(stock_icon["parent_icon"], workspace.ERPNEXT_DESKTOP_ICON)
        self.assertEqual(stock_icon.save_count, 1)

    def test_desktop_icons_are_untouched_without_an_erpnext_stock_icon(self) -> None:
        with (
            patch.object(workspace.frappe.db, "exists", return_value=False),
            patch.object(workspace.frappe.db, "get_value") as get_value,
            patch.object(workspace.frappe, "get_doc") as get_doc,
        ):
            workspace.ensure_desktop_icons()

        get_value.assert_not_called()
        get_doc.assert_not_called()

    def test_regulatory_navigation_preserves_unmanaged_rows(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()
        workspaces[workspace.REGULATORY_WORKSPACE]["links"] = [
            frappe._dict({"type": "Card Break", "label": "Custom Shortcuts"}),
            frappe._dict(
                {
                    "type": "Link",
                    "label": "Custom Regulatory Tool",
                    "link_type": "Page",
                    "link_to": "custom-regulatory-tool",
                }
            ),
        ]
        sidebars[workspace.REGULATORY_WORKSPACE]["items"] = [
            sidebar_link("Custom Regulatory Tool"),
        ]
        sidebars[workspace.REGULATORY_WORKSPACE]["items"][0].update(
            {"link_type": "Page", "link_to": "custom-regulatory-tool"}
        )

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
        ):
            workspace.ensure_workspace_navigation()
            workspace.ensure_workspace_navigation()

        self.assertEqual(
            sum(
                row.get("link_to") == "custom-regulatory-tool"
                for row in workspaces[workspace.REGULATORY_WORKSPACE]["links"]
            ),
            1,
        )
        self.assertEqual(
            sum(
                row.get("link_to") == "custom-regulatory-tool"
                for row in sidebars[workspace.REGULATORY_WORKSPACE]["items"]
            ),
            1,
        )

    def test_regulatory_sidebar_customizations_survive_standard_sync(self) -> None:
        custom_row = frappe._dict(
            {
                "type": "Link",
                "label": "Custom Regulatory Tool",
                "link_type": "Page",
                "link_to": "custom-regulatory-tool",
                "child": 0,
                "icon": "tool",
            }
        )
        sidebar = FakeDocument(name=workspace.REGULATORY_WORKSPACE, items=[custom_row])

        with (
            patch.object(workspace.frappe.db, "exists", return_value=True),
            patch.object(workspace.frappe, "get_doc", return_value=sidebar),
        ):
            workspace.snapshot_regulatory_sidebar_customizations()
            sidebar["items"] = []
            workspace.restore_regulatory_sidebar_customizations()

        self.assertEqual(
            [row.get("link_to") for row in sidebar["items"]],
            ["custom-regulatory-tool"],
        )
        self.assertEqual(sidebar.save_count, 1)

    def test_regulatory_workspace_customizations_survive_orphan_cleanup(self) -> None:
        custom_row = frappe._dict(
            {
                "type": "Link",
                "label": "Custom Regulatory Report",
                "link_type": "Page",
                "link_to": "custom-regulatory-report",
                "icon": "file-chart-column",
                "hidden": 1,
                "dependencies": "custom_app",
                "only_for": "Thailand",
                "onboard": 1,
                "description": "Custom report shortcut",
            }
        )
        workspace_doc = FakeDocument(
            name=workspace.REGULATORY_WORKSPACE,
            links=[custom_row],
            content='[{"type":"card","data":{"card_name":"Custom Shortcuts","col":4}}]',
            shortcuts=[frappe._dict({"type": "DocType", "label": "Custom Shortcut", "link_to": "Item"})],
            charts=[frappe._dict({"chart_name": "Custom Chart"})],
            quick_lists=[frappe._dict({"document_type": "Item"})],
            number_cards=[frappe._dict({"label": "Custom Count", "document_type": "Item"})],
            custom_blocks=[frappe._dict({"label": "Custom Block", "html": "<p>Custom</p>"})],
            roles=[frappe._dict({"role": "Regulatory Viewer"})],
        )

        with (
            patch.object(workspace.frappe.db, "exists", return_value=True),
            patch.object(workspace.frappe, "get_doc", return_value=workspace_doc),
        ):
            workspace.snapshot_regulatory_workspace_customizations()
            workspace_doc["links"] = []
            workspace_doc["content"] = "[]"
            for fieldname in workspace.WORKSPACE_CHILD_TABLE_FIELDS:
                workspace_doc[fieldname] = []
            workspace.restore_regulatory_workspace_customizations()

        self.assertEqual(
            [row.get("link_to") for row in workspace_doc["links"]],
            ["custom-regulatory-report"],
        )
        self.assertEqual(workspace_doc["links"][0]["icon"], "file-chart-column")
        self.assertEqual(workspace_doc["links"][0]["description"], "Custom report shortcut")
        self.assertEqual(
            json.loads(workspace_doc["content"])[0]["data"]["card_name"],
            "Custom Shortcuts",
        )
        self.assertEqual(workspace_doc["shortcuts"][0]["label"], "Custom Shortcut")
        self.assertEqual(workspace_doc["charts"][0]["chart_name"], "Custom Chart")
        self.assertEqual(workspace_doc["quick_lists"][0]["document_type"], "Item")
        self.assertEqual(workspace_doc["number_cards"][0]["label"], "Custom Count")
        self.assertEqual(workspace_doc["custom_blocks"][0]["label"], "Custom Block")
        self.assertEqual(workspace_doc["roles"][0]["role"], "Regulatory Viewer")
        self.assertEqual(workspace_doc.save_count, 1)

    def test_regulatory_navigation_preserves_custom_generic_card_names(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()
        workspaces[workspace.REGULATORY_WORKSPACE]["links"] = [
            frappe._dict({"type": "Card Break", "label": "Reports"}),
            frappe._dict(
                {
                    "type": "Link",
                    "label": "Custom Report",
                    "link_type": "Page",
                    "link_to": "custom-report",
                }
            ),
        ]
        workspaces[workspace.REGULATORY_WORKSPACE]["content"] = json.dumps(
            [{"type": "card", "data": {"card_name": "Reports", "col": 4}}]
        )

        with (
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: get_document(workspaces, sidebars, doctype, name),
            ),
            patch.object(workspace.frappe.db, "exists", side_effect=existing_document),
        ):
            workspace.ensure_workspace_navigation()
            workspace.ensure_workspace_navigation()

        self.assertEqual(
            sum(row.get("label") == "Reports" for row in workspaces[workspace.REGULATORY_WORKSPACE]["links"]),
            2,
        )
        self.assertEqual(
            sum(
                block.get("data", {}).get("card_name") == "Reports"
                for block in json.loads(workspaces[workspace.REGULATORY_WORKSPACE]["content"])
            ),
            2,
        )

    def test_legacy_regulatory_navigation_is_renamed(self) -> None:
        existing = {
            ("Workspace", workspace.LEGACY_REGULATORY_WORKSPACE),
            ("Workspace Sidebar", workspace.LEGACY_REGULATORY_WORKSPACE),
        }

        def exists(doctype: str, name: str) -> bool:
            return (doctype, name) in existing

        def rename(doctype: str, old: str, new: str, **_: Any) -> None:
            existing.remove((doctype, old))
            existing.add((doctype, new))

        renamed_docs = [
            FakeDocument(
                name=workspace.REGULATORY_WORKSPACE,
                label=workspace.LEGACY_REGULATORY_WORKSPACE,
                title=workspace.LEGACY_REGULATORY_WORKSPACE,
                module=workspace.REGULATORY_MODULE,
                icon="",
            ),
            FakeDocument(
                name=workspace.REGULATORY_WORKSPACE,
                title=workspace.LEGACY_REGULATORY_WORKSPACE,
                module=workspace.REGULATORY_MODULE,
                header_icon="",
            ),
        ]

        with (
            patch.object(workspace.frappe.db, "exists", side_effect=exists),
            patch.object(workspace.frappe, "rename_doc", side_effect=rename) as rename_doc,
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=renamed_docs,
            ),
        ):
            workspace._migrate_legacy_regulatory_navigation()

        self.assertEqual(rename_doc.call_count, 2)
        self.assertEqual(renamed_docs[0]["label"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(renamed_docs[0]["title"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(renamed_docs[0]["icon"], workspace.REGULATORY_ICON)
        self.assertEqual(renamed_docs[1]["title"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(renamed_docs[1]["header_icon"], workspace.REGULATORY_ICON)
        self.assertEqual(
            [(call.args[0], call.args[1], call.args[2]) for call in rename_doc.call_args_list],
            [
                ("Workspace", workspace.LEGACY_REGULATORY_WORKSPACE, workspace.REGULATORY_WORKSPACE),
                (
                    "Workspace Sidebar",
                    workspace.LEGACY_REGULATORY_WORKSPACE,
                    workspace.REGULATORY_WORKSPACE,
                ),
            ],
        )

    def test_legacy_regulatory_navigation_is_removed_when_new_target_exists(self) -> None:
        workspaces = workspace_documents()
        sidebars = sidebar_documents()
        legacy_workspace = FakeDocument(
            name=workspace.LEGACY_REGULATORY_WORKSPACE,
            links=[
                frappe._dict({"type": "Card Break", "label": "Legacy Custom"}),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "Legacy Custom",
                        "link_type": "Page",
                        "link_to": "legacy-custom",
                    }
                ),
            ],
            content='[{"type":"card","data":{"card_name":"Legacy Custom","col":4}}]',
        )
        legacy_sidebar = FakeDocument(
            name=workspace.LEGACY_REGULATORY_WORKSPACE,
            items=[
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "Legacy Custom",
                        "link_type": "Page",
                        "link_to": "legacy-custom",
                    }
                )
            ],
        )
        workspaces[workspace.LEGACY_REGULATORY_WORKSPACE] = legacy_workspace
        sidebars[workspace.LEGACY_REGULATORY_WORKSPACE] = legacy_sidebar

        with (
            patch.object(
                workspace.frappe.db,
                "exists",
                return_value=True,
            ),
            patch.object(
                workspace.frappe,
                "get_doc",
                side_effect=lambda doctype, name: (
                    workspaces[name] if doctype == "Workspace" else sidebars[name]
                ),
            ),
            patch.object(workspace.frappe, "delete_doc") as delete_doc,
        ):
            workspace._migrate_legacy_regulatory_navigation()

        self.assertEqual(
            [(call.args[0], call.args[1]) for call in delete_doc.call_args_list],
            [
                ("Workspace", workspace.LEGACY_REGULATORY_WORKSPACE),
                ("Workspace Sidebar", workspace.LEGACY_REGULATORY_WORKSPACE),
            ],
        )
        self.assertEqual(workspaces[workspace.REGULATORY_WORKSPACE]["links"][1]["link_to"], "legacy-custom")
        self.assertEqual(sidebars[workspace.REGULATORY_WORKSPACE]["items"][0]["link_to"], "legacy-custom")

    def test_regulatory_desktop_icon_opens_the_workspace_sidebar(self) -> None:
        desktop_icon_path = Path(__file__).parents[2] / "desktop_icon" / "regulatory.json"
        desktop_icon = json.loads(desktop_icon_path.read_text())
        self.assertEqual(desktop_icon["doctype"], "Desktop Icon")
        self.assertEqual(desktop_icon["name"], workspace.REGULATORY_WORKSPACE)
        self.assertTrue(desktop_icon["modified"])
        self.assertEqual(desktop_icon["label"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(desktop_icon["link_to"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(desktop_icon["link_type"], "Workspace Sidebar")
        for variant in ("subtle", "solid"):
            self.assertTrue(
                (
                    Path(__file__).parents[2]
                    / "public"
                    / "icons"
                    / "desktop_icons"
                    / variant
                    / "regulatory.svg"
                ).is_file()
            )

    def test_legacy_desktop_icon_is_retargeted(self) -> None:
        legacy_icon = FakeDocument(
            name=workspace.LEGACY_REGULATORY_WORKSPACE,
            label=workspace.LEGACY_REGULATORY_WORKSPACE,
            link_type="Workspace Sidebar",
            link_to=workspace.LEGACY_REGULATORY_WORKSPACE,
            icon="old-icon",
        )

        with (
            patch.object(
                workspace.frappe,
                "get_all",
                return_value=[workspace.LEGACY_REGULATORY_WORKSPACE],
            ),
            patch.object(workspace.frappe.db, "exists", return_value=False),
            patch.object(workspace.frappe, "get_doc", return_value=legacy_icon),
        ):
            workspace._migrate_legacy_regulatory_desktop_icons()

        self.assertEqual(legacy_icon["label"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(legacy_icon["link_to"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(legacy_icon["icon"], workspace.REGULATORY_ICON)
        self.assertEqual(legacy_icon.save_count, 1)

    def test_legacy_personalized_sidebar_is_renamed_and_retargeted(self) -> None:
        old_name = f"{workspace.LEGACY_REGULATORY_WORKSPACE}-user@example.com"
        sidebar = FakeDocument(
            name=old_name,
            title=old_name,
            module=workspace.REGULATORY_MODULE,
            header_icon="old-icon",
            for_user="user@example.com",
            items=[
                frappe._dict(
                    {
                        "type": "Link",
                        "link_type": "Workspace",
                        "link_to": workspace.LEGACY_REGULATORY_WORKSPACE,
                    }
                ),
                sidebar_link("Custom Tool"),
            ],
        )
        new_name = f"{workspace.REGULATORY_WORKSPACE}-user@example.com"

        with (
            patch.object(workspace.frappe, "get_all", return_value=[old_name]),
            patch.object(workspace.frappe.db, "exists", return_value=False),
            patch.object(workspace.frappe, "rename_doc") as rename_doc,
            patch.object(workspace.frappe, "get_doc", return_value=sidebar),
        ):
            workspace._migrate_legacy_regulatory_personalized_sidebars()

        self.assertEqual(rename_doc.call_args.args[:3], ("Workspace Sidebar", old_name, new_name))
        self.assertEqual(sidebar["title"], new_name)
        self.assertEqual(sidebar["module"], workspace.REGULATORY_MODULE)
        self.assertEqual(sidebar["items"][0]["link_to"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(sidebar["items"][1]["link_to"], "Custom Tool")
        self.assertEqual(sidebar.save_count, 1)

    def test_legacy_desktop_icon_customization_is_merged_into_standard_icon(self) -> None:
        legacy_icon = FakeDocument(
            name=workspace.LEGACY_REGULATORY_WORKSPACE,
            label=workspace.LEGACY_REGULATORY_WORKSPACE,
            link_type="Workspace Sidebar",
            link_to=workspace.LEGACY_REGULATORY_WORKSPACE,
            icon="custom-icon",
            parent_icon="Custom Parent",
            idx=7,
            roles=[frappe._dict({"role": "Regulatory Viewer"})],
        )
        target_icon = FakeDocument(
            name=workspace.REGULATORY_WORKSPACE,
            label=workspace.REGULATORY_WORKSPACE,
            link_type="Workspace Sidebar",
            link_to=workspace.REGULATORY_WORKSPACE,
            icon=workspace.REGULATORY_ICON,
        )

        with (
            patch.object(workspace.frappe, "get_all", return_value=[legacy_icon["name"]]),
            patch.object(workspace.frappe.db, "exists", return_value=True),
            patch.object(workspace.frappe, "get_doc", side_effect=[legacy_icon, target_icon]),
            patch.object(workspace.frappe, "delete_doc") as delete_doc,
        ):
            workspace._migrate_legacy_regulatory_desktop_icons()

        self.assertEqual(target_icon["icon"], "custom-icon")
        self.assertEqual(target_icon["parent_icon"], "Custom Parent")
        self.assertEqual(target_icon["idx"], 7)
        self.assertEqual(target_icon["roles"][0]["role"], "Regulatory Viewer")
        self.assertEqual(target_icon.save_count, 1)
        self.assertEqual(
            delete_doc.call_args.args[:2], ("Desktop Icon", workspace.LEGACY_REGULATORY_WORKSPACE)
        )

    def test_legacy_user_desktop_icon_is_retargeted_without_changing_standard_icon(self) -> None:
        legacy_icon = FakeDocument(
            name="user-regulatory-icon",
            label=workspace.LEGACY_REGULATORY_WORKSPACE,
            standard=0,
            link_type="Workspace Sidebar",
            link_to=workspace.LEGACY_REGULATORY_WORKSPACE,
            icon="custom-icon",
            owner="user@example.com",
            idx=7,
            hidden=1,
        )
        target_icon = FakeDocument(
            name=workspace.REGULATORY_WORKSPACE,
            label=workspace.REGULATORY_WORKSPACE,
            standard=1,
            link_type="Workspace Sidebar",
            link_to=workspace.REGULATORY_WORKSPACE,
            icon=workspace.REGULATORY_ICON,
        )

        with (
            patch.object(workspace.frappe, "get_all", return_value=[legacy_icon["name"]]),
            patch.object(workspace.frappe.db, "exists", return_value=True),
            patch.object(workspace.frappe, "get_doc", side_effect=[legacy_icon, target_icon]),
            patch.object(workspace.frappe, "delete_doc") as delete_doc,
        ):
            workspace._migrate_legacy_regulatory_desktop_icons()

        self.assertEqual(legacy_icon["link_to"], workspace.REGULATORY_WORKSPACE)
        self.assertEqual(legacy_icon["icon"], "custom-icon")
        self.assertEqual(legacy_icon.save_count, 1)
        self.assertEqual(target_icon.save_count, 0)
        delete_doc.assert_not_called()

    def test_regulatory_sidebar_keeps_custom_children_inside_managed_sections(self) -> None:
        custom_row = frappe._dict(
            {
                "type": "Link",
                "label": "Custom Report",
                "link_type": "Page",
                "link_to": "custom-report",
                "child": 1,
            }
        )
        items = [frappe._dict(row) for row in workspace._regulatory_sidebar_items()]
        reports_index = next(
            index
            for index, row in enumerate(items)
            if row.get("type") == "Section Break" and row.get("label") == "Reports"
        )
        items.insert(reports_index + 2, custom_row)
        sidebar = FakeDocument(name=workspace.REGULATORY_WORKSPACE, items=items)

        self.assertTrue(workspace._ensure_regulatory_sidebar(cast(Document, sidebar)))
        self.assertFalse(workspace._ensure_regulatory_sidebar(cast(Document, sidebar)))

        report_sections = [
            index
            for index, row in enumerate(sidebar["items"])
            if row.get("type") == "Section Break" and row.get("label") == "Reports"
        ]
        self.assertEqual(len(report_sections), 1)
        report_end = next(
            (
                index
                for index in range(report_sections[0] + 1, len(sidebar["items"]))
                if sidebar["items"][index].get("type") == "Section Break"
            ),
            len(sidebar["items"]),
        )
        report_rows = sidebar["items"][report_sections[0] + 1 : report_end]
        self.assertEqual(sum(row.get("link_to") == "custom-report" for row in report_rows), 1)
        self.assertEqual(
            sum(row.get("link_to") == "Medical Device Registration Expiry Summary" for row in report_rows),
            1,
        )

    def test_regulatory_sidebar_reconciles_a_partial_section_without_detaching_custom_rows(self) -> None:
        custom_row = frappe._dict(
            {
                "type": "Link",
                "label": "Custom Report",
                "link_type": "Page",
                "link_to": "custom-report",
                "child": 1,
            }
        )
        items = [frappe._dict(row) for row in workspace._regulatory_sidebar_items()]
        reports_index = next(
            index
            for index, row in enumerate(items)
            if row.get("type") == "Section Break" and row.get("label") == "Reports"
        )
        setup_index = next(
            index
            for index, row in enumerate(items)
            if row.get("type") == "Section Break" and row.get("label") == "Setup"
        )
        items.insert(reports_index + 2, custom_row)
        del items[setup_index + 1 : setup_index + 3]
        sidebar = FakeDocument(name=workspace.REGULATORY_WORKSPACE, items=items)

        self.assertTrue(workspace._ensure_regulatory_sidebar(cast(Document, sidebar)))
        reports_index = next(
            index
            for index, row in enumerate(sidebar["items"])
            if row.get("type") == "Section Break" and row.get("label") == "Reports"
        )
        setup_index = next(
            index
            for index, row in enumerate(sidebar["items"])
            if row.get("type") == "Section Break" and row.get("label") == "Setup"
        )
        self.assertLess(reports_index, setup_index)
        report_rows = sidebar["items"][reports_index + 1 : setup_index]
        self.assertEqual(sum(row.get("link_to") == "custom-report" for row in report_rows), 1)

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
            [row["link_to"] for row in sidebar["items"][item_index + 1 : item_index + 4]],
            ["DKSH Item", "Product Group", "Storage Condition"],
        )
        self.assertTrue(all(row["child"] == 1 for row in sidebar["items"][item_index + 1 : item_index + 4]))

    def test_existing_workspace_card_links_are_reordered_by_priority(self) -> None:
        workspace_doc = FakeDocument(
            name="Stock",
            parent_page="",
            links=[
                frappe._dict({"type": "Card Break", "label": workspace.NAVIGATION_LABEL}),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "Storage Condition",
                        "link_type": "DocType",
                        "link_to": "Storage Condition",
                    }
                ),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "Back Orders",
                        "link_type": "Report",
                        "link_to": "Back Orders",
                        "report_ref_doctype": "Sales Order",
                        "is_query_report": 1,
                    }
                ),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "DKSH Item",
                        "link_type": "DocType",
                        "link_to": "DKSH Item",
                    }
                ),
                frappe._dict(
                    {
                        "type": "Link",
                        "label": "Product Group",
                        "link_type": "DocType",
                        "link_to": "Product Group",
                    }
                ),
            ],
            content='[{"type":"card","data":{"card_name":"Connect Diagnostics","col":4}}]',
        )
        group = next(group for group in workspace.NAVIGATION_GROUPS if group.name == "Stock")

        changed = workspace._ensure_workspace_card(cast(Document, workspace_doc), group)

        self.assertTrue(changed)
        self.assertEqual(
            [row.get("link_to") for row in workspace_doc["links"][1:]],
            [link.link_to for link in group.links],
        )

    def test_empty_group_removes_existing_card_break_and_content_block(self) -> None:
        # By the time _ensure_workspace_card runs, _remove_retired_card_links has
        # already stripped any stale report/doctype Link rows — only the now-empty
        # "Connect Diagnostics" Card Break and its content block are left to tear down.
        workspace_doc = FakeDocument(
            name="Financial Reports",
            parent_page="",
            links=[frappe._dict({"type": "Card Break", "label": workspace.NAVIGATION_LABEL})],
            content='[{"type":"card","data":{"card_name":"Connect Diagnostics","col":4}}]',
        )
        group = next(group for group in workspace.NAVIGATION_GROUPS if group.name == "Financial Reports")

        changed = workspace._ensure_workspace_card(cast(Document, workspace_doc), group)

        self.assertTrue(changed)
        self.assertEqual(workspace_doc["links"], [])
        self.assertEqual(json.loads(workspace_doc["content"]), [])

    def test_retired_report_card_link_is_removed_from_financial_reports(self) -> None:
        workspace_doc = FakeDocument(
            name="Financial Reports",
            links=[
                frappe._dict(
                    {
                        "type": "Link",
                        "link_type": "Report",
                        "link_to": "General Ledger TH",
                    }
                ),
                frappe._dict(
                    {
                        "type": "Link",
                        "link_type": "Report",
                        "link_to": "Trial Balance",
                    }
                ),
            ],
        )

        changed = workspace._remove_retired_card_links(cast(Document, workspace_doc), "Financial Reports")

        self.assertTrue(changed)
        self.assertEqual([row["link_to"] for row in workspace_doc["links"]], ["Trial Balance"])
