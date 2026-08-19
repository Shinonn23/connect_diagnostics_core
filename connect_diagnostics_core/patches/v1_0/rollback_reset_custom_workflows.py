"""Rollback for reset_custom_workflows — intentionally a no-op.

The custom-workflow reset removed the workflow definitions from the app's code
(setup provisioning and fixtures) as well as from the database. Those definitions
no longer exist anywhere in this app, so this patch cannot reconstruct the deleted
Workflow, Workflow State, or Workflow Action Master records.

To restore the previous approval behaviour, revert the reset commits (Phase 1 and
Phase 2) and run ``bench migrate``; the restored provisioning code recreates the
Workflows. This file exists to satisfy the paired-rollback convention and records
that recovery is by source revert, not by re-running a patch.
"""

import frappe


def execute():
    frappe.logger(__name__).info(
        "rollback_reset_custom_workflows is a no-op; restore workflows by reverting "
        "the custom-workflow reset commits and running bench migrate."
    )
