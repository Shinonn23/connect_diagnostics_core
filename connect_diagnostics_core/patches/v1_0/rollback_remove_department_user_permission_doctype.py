# Copyright (c) 2026, Siwat Sroisuwan and contributors
# For license information, please see license.txt

"""Rollback for remove_department_user_permission_doctype.

Both DocTypes have real controller/JS files on disk (``apply_permissions`` /
``remove_permissions`` / ``get_employees_in_department`` in the .py, the
Apply/Remove Permissions buttons in the .js), so recreating only the DocType
metadata row here would leave a DocType with no working buttons or whitelisted
methods. A correct rollback must restore the source files, not just DB rows.
To restore:

1. Restore both doctype folders from git history (before the commit that
   removed them) under
   ``connect_diagnostics_core/doctype/{department_user_permission,
   department_user_permission_user}``.
2. Restore the "ERPNext Settings" ``NavigationGroup``/``SidebarPlacement``
   entries and the ``RETIRED_SIDEBAR_LINKS`` / ``RETIRED_CARD_LINKS`` removals
   in ``setup/workspace.py``.
3. Run ``bench migrate`` — Frappe reimports the DocTypes from source and
   ``ensure_workspace_navigation`` re-adds their shortcuts.

Any ``User Permission`` records the tool previously created were never
touched by the removal patch, so nothing needs restoring there.

Not registered in patches.txt (manual rollback utility only), matching the
existing rollback_remove_customer_name_th_field.py convention.
"""

import frappe
from frappe import _


def execute():
    frappe.throw(
        _(
            "Restoring Department User Permission requires restoring both doctype folders and "
            "the setup/workspace.py navigation entries from git history, then re-running "
            "`bench migrate` — see this file's module docstring. There is nothing this script "
            "can do purely against the database."
        )
    )
