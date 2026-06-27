# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class GitHubHelpdeskSyncSettings(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        from connect_diagnostics_core.connect_diagnostics_core.doctype.github_status_mapping.github_status_mapping import (
            GitHubStatusMapping,
        )
        from connect_diagnostics_core.connect_diagnostics_core.doctype.github_user_map.github_user_map import (
            GitHubUserMap,
        )

        auth_method: DF.Literal["GitHub CLI (gh)", "Personal Access Token"]
        connection_status: DF.SmallText | None
        enabled: DF.Check
        gh_path: DF.Data | None
        github_owner: DF.Data
        github_repo: DF.Data
        github_token: DF.Password | None
        github_user_map: DF.Table[GitHubUserMap]
        last_pull: DF.Data | None
        last_pull_status: DF.SmallText | None
        project_id: DF.Data | None
        project_number: DF.Int
        pull_enabled: DF.Check
        resolved_status: DF.Link | None
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
        frappe.db.set_single_value("GitHub Helpdesk Sync Settings", "connection_status", msg)
        return info
    except Exception as e:
        frappe.db.set_single_value(
            "GitHub Helpdesk Sync Settings", "connection_status", _("FAILED: {0}").format(str(e))
        )
        return {"ok": False, "error": str(e)}


@frappe.whitelist()
def fetch_board_metadata():
    """Pull the Project v2 node id, Status field id and option ids into the settings."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    return g.refresh_project_metadata()


@frappe.whitelist()
def sync_now():
    """Run a GitHub → Helpdesk pull immediately (foreground)."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    return g.pull(run_type="Manual Pull")


@frappe.whitelist()
def preflight_check():
    """Validate GitHub integration setup without mutating synced records."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    return g.preflight_check()


@frappe.whitelist()
def repair_setup():
    """Repair local custom fields and refresh GitHub project metadata."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    return g.repair_setup()


@frappe.whitelist()
def retry_issue(issue_number: int):
    """Pull one GitHub issue immediately."""
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    return g.retry_issue(int(issue_number))


@frappe.whitelist()
def import_backlog(commit: int = 0):
    """One-off bootstrap: create HD Tickets for GitHub issues that have none yet.

    Pass commit=0 (default) for a dry-run preview, commit=1 to actually create them.
    Idempotent — issues already linked to a ticket are skipped.
    """
    from connect_diagnostics_core import github_sync as g

    frappe.only_for("System Manager")
    return g.import_from_github(commit=bool(frappe.utils.cint(commit)))
