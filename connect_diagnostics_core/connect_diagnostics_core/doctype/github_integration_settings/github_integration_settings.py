# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class GitHubIntegrationSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from connect_diagnostics_core.connect_diagnostics_core.doctype.github_status_mapping.github_status_mapping import (
            GitHubStatusMapping,
        )

        auth_method: DF.Literal["GitHub CLI (gh)", "Personal Access Token"]
        comment_attribution: DF.Literal["Token owner + agent name", "Token owner only"]
        connection_status: DF.SmallText | None
        gh_path: DF.Data | None
        enabled: DF.Check
        github_owner: DF.Data
        github_repo: DF.Data
        github_token: DF.Password | None
        last_pull: DF.Data | None
        last_pull_status: DF.SmallText | None
        project_id: DF.Data | None
        project_number: DF.Int
        pull_enabled: DF.Check
        push_close_state: DF.Check
        push_comments: DF.Check
        push_status_to_board: DF.Check
        status_field_id: DF.Data | None
        status_mappings: DF.Table[GitHubStatusMapping]
    # end: auto-generated types
    pass


@frappe.whitelist()
def test_connection():
    """Verify access (via gh CLI or token) and report granted scopes."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    try:
        info = g.connection_info()
        msg = _("OK — connected to {0} via {1}. Scopes: {2}").format(
            info.get("target"), info.get("transport"), info.get("scopes") or "(unknown)"
        )
        if not info.get("can_push_board"):
            msg += "\n" + _("⚠ Board-status push needs the 'project' scope. Run: gh auth refresh -s project")
        frappe.db.set_single_value("GitHub Integration Settings", "connection_status", msg)
        return info
    except Exception as e:
        frappe.db.set_single_value(
            "GitHub Integration Settings", "connection_status", _("FAILED: {0}").format(str(e))
        )
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def fetch_board_metadata():
    """Pull the Project v2 node id, Status field id and option ids into the settings."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    meta = g.fetch_project_metadata()
    doc = frappe.get_single("GitHub Integration Settings")
    doc.project_id = meta["project_id"]
    doc.status_field_id = meta["status_field_id"]
    doc.status_mappings = []
    for name, option_id in meta["options"].items():
        doc.append(
            "status_mappings",
            {
                "board_column": name,
                "option_id": option_id,
                "hd_status": name if frappe.db.exists("HD Ticket Status", name) else None,
                "category": g.BOARD_CATEGORY.get(name, "Open"),
            },
        )
    doc.save(ignore_permissions=True)
    return {"options": len(meta["options"])}


@frappe.whitelist()
def sync_now():
    """Run a GitHub → Helpdesk pull immediately (foreground)."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    return g.pull()
